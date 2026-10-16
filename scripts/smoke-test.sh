#!/usr/bin/env bash
# Prueba de humo del despliegue con Docker: levanta la app con PostgreSQL y comprueba que
# el frontend, la API, el admin y el inicio de sesión (cookie + CSRF, mismo dominio) funcionan.
# Uso: scripts/smoke-test.sh   (necesita Docker; lo ejecuta el CI en cada PR)
set -eu  # sin pipefail: "grep -q" cierra la tubería antes y curl daría un falso error
cd "$(dirname "$0")/.."

BASE=http://localhost:8000
JAR=$(mktemp)
fail() { echo "FALLÓ: $*" >&2; docker compose logs app | tail -50 >&2; exit 1; }

if [ ! -f .env ]; then
  cat > .env <<ENV
DJANGO_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
DJANGO_ALLOWED_HOSTS=localhost
CSRF_TRUSTED_ORIGINS=$BASE
DJANGO_SECURE_COOKIES=0
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
ENV
  echo "Creado .env de prueba (sin HTTPS)."
fi

docker compose up -d --build

echo "Esperando a que la app responda…"
for _ in $(seq 1 60); do
  curl -fs "$BASE/api/health/" >/dev/null && break
  sleep 2
done
curl -fs "$BASE/api/health/" | grep -q '"database":true' || fail "health no responde con la base de datos"
echo "✓ /api/health/ con PostgreSQL"

curl -fs "$BASE/" | grep -q "<title>Inventario POS</title>" || fail "la raíz no sirve el frontend"
echo "✓ / sirve el frontend"

curl -fs "$BASE/sw.js" | grep -q "pos-app" || fail "no se sirve el service worker"
curl -fsI "$BASE/sw.js" | grep -qi "immutable" && fail "sw.js no debe guardarse en caché para siempre"
echo "✓ /sw.js sin caché permanente"

ASSET=$(curl -fs "$BASE/" | grep -o '/assets/[^"]*\.js' | head -1)
curl -fsI "$BASE$ASSET" | grep -qi "immutable" || fail "los assets con hash deberían ser inmutables ($ASSET)"
echo "✓ $ASSET con caché inmutable"

curl -fs "$BASE/admin/login/" | grep -q "csrfmiddlewaretoken" || fail "admin no responde"
CSS=$(curl -fs "$BASE/admin/login/" | grep -o '/static/admin/css/[^"]*\.css' | head -1)
curl -fs -o /dev/null "$BASE$CSS" || fail "no se sirven los estáticos del admin ($CSS)"
echo "✓ admin y sus estáticos ($CSS)"

# Usuario de prueba con rol Caja (solo existe en esta base de prueba).
PW=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
docker compose exec -T app python manage.py shell -c "
from apps.accounts.models import Role, User
u, _ = User.objects.get_or_create(username='humo')
u.set_password('$PW'); u.save(); u.roles.set([Role.objects.get(name='Caja')])
" >/dev/null

curl -fs -c "$JAR" -b "$JAR" "$BASE/api/auth/csrf/" >/dev/null
TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$JAR")
[ -n "$TOKEN" ] || fail "no llegó la cookie csrftoken"
curl -fs -c "$JAR" -b "$JAR" -H "Content-Type: application/json" -H "X-CSRFToken: $TOKEN" -H "Origin: $BASE" \
  -d "{\"username\":\"humo\",\"password\":\"$PW\"}" "$BASE/api/auth/login/" | grep -q '"cash.operate"' \
  || fail "el inicio de sesión no funcionó"
curl -fs -b "$JAR" "$BASE/api/auth/me/" | grep -q '"username":"humo"' || fail "la sesión no se mantuvo"
curl -fs -b "$JAR" "$BASE/api/cash/registers/" >/dev/null || fail "la API con sesión no respondió"
echo "✓ inicio de sesión con cookie + CSRF y API con sesión"

rm -f "$JAR"
echo "Todo bien."
