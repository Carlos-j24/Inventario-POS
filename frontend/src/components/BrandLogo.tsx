import { useState } from "react";

/** El logo del negocio lo trae cada instalación (BRAND_DIR en el servidor). */
export const LOGO_URL = "/brand/logo.png";

/**
 * Logo del negocio: si la instalación no trae uno (la ferretería), el servidor responde 404 y no se
 * muestra nada. El service worker lo guarda para verlo sin conexión.
 */
export default function BrandLogo({ className, alt = "" }: { className: string; alt?: string }) {
  const [missing, setMissing] = useState(false);
  if (missing) return null;
  return <img src={LOGO_URL} className={className} alt={alt} onError={() => setMissing(true)} />;
}
