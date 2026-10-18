# Proveedores tecnológicos DIAN para la T7

> Investigación del 2026-10-17 para elegir el proveedor de la spec 005 (decisión 1: proveedor tecnológico por API). Fuentes: páginas de cada proveedor y el **listado oficial de la DIAN** (archivo `Proveedores-habilitados-15102026.xlsx`, 96 empresas). Precios en pesos colombianos, sin IVA salvo que se diga; son de páginas comerciales y pueden cambiar: **hay que confirmarlos por escrito antes de contratar**.

## Qué necesitamos del proveedor
Lo que ya hace nuestro sistema (T1–T6) define lo que el adaptador (`invoicing/providers/`) le pide al proveedor:

1. **Documento equivalente electrónico POS por API**, no solo factura: es el documento por defecto de la caja (decisión 2). Con su **nota de ajuste** para anulaciones y devoluciones.
2. Factura electrónica y nota crédito, para los clientes que la pidan.
3. **Respuesta síncrona con CUDE/CUFE y QR** (el tiquete se imprime ya validado, T6).
4. **Contingencia**: transmitir después de la venta los documentos emitidos sin conexión (art. 37), con nuestra numeración de contingencia (T5).
5. Usar **nuestra numeración por caja** (prefijo y consecutivo los pone el POS, T2).
6. Sandbox para el set de pruebas de habilitación.
7. Costo razonable a volumen de ferretería: entre 50 y 200 tiquetes al día, unos **20.000 a 70.000 documentos al año**.
8. Pensando en el negocio del equipo (vender el sistema a varios comercios): **varias empresas (NIT)** con una sola integración.

## El dato más importante: quién está en el listado oficial
Un proveedor tecnológico es una empresa habilitada por resolución de la DIAN. Varias marcas que se anuncian como "proveedor autorizado" **no aparecen por su nombre** en el listado oficial; pueden operar con otra razón social o revender a otro proveedor, pero eso hay que verificarlo (resolución de habilitación y NIT) antes de confiarles la facturación.

| Marca | ¿En el listado DIAN? |
|---|---|
| Dataico | ✅ DATAICO S.A.S (NIT 901223648) |
| Alegra | ✅ SOLUCIONES ALEGRA S.A.S (NIT 900559088) |
| The Factory HKA | ✅ THE FACTORY HKA COLOMBIA S.A.S. (NIT 900390126) |
| Carvajal | ✅ CARVAJAL TECNOLOGÍA Y SERVICIOS S.A.S. (NIT 890321151) |
| Siigo, Edicom | ✅ (orientados a su propio ERP o a grandes empresas) |
| Plemsi, Factus (Halltec), Alanube, Bilidox | ❌ no aparecen por nombre: pedir resolución y NIT |
| MATIAS API | No aplica: no es proveedor tecnológico, funciona como **software propio** (ver abajo) |

## Comparación

| | **The Factory HKA** | **Dataico** | **Alegra API** | **Plemsi** | **MATIAS API** | **Factus** | **Alanube** |
|---|---|---|---|---|---|---|---|
| En el listado DIAN | ✅ | ✅ | ✅ | ❌ sin verificar | Software propio | ❌ sin verificar | ❌ sin verificar |
| DE-POS por API | ✅ documentos equivalentes (Res. 165) en su manual de integración | Parece que sí: su API lista "POS electrónico" y notas de ajuste POS; falta ver el endpoint | En su producto sí; en la API **no confirmado** | Incluye "POS Electrónico" en los paquetes | ✅ "POS electrónico" | ❌ no aparece en su documentación | No lo menciona |
| Contingencia | ✅ documentada: tipo 03 por el método Enviar, 48 h, numeración del emisor | No documentada en lo revisado | No documentada | No documentada | No documentada | "Contingencia Tipo 03" en la API (solo factura) | Reenvío automático al volver la DIAN |
| API | REST (y servicio web), manual público | REST v2 (`/v2/invoices`), token de cuenta | REST, sandbox 24 h | REST, documentación en Postman | REST, JWT, Swagger, sandbox | REST, OAuth2, sandbox compartido gratis | REST, sandbox a solicitud |
| Varias empresas | Programa de integradores | API para "documentos de tus clientes" | Por empresa | Bolsas multiempresa a consulta | ✅ sin límite de NIT | Por empresa | Para casas de software |
| Precio publicado | ❌ cotización | ❌ cotización | ❌ cotización | ✅ | ✅ | ❌ cotización | Pago por uso, cotización |

### Costo estimado a volumen de ferretería (con precios publicados)

| Proveedor | ~24.000 docs/año | ~60.000 docs/año |
|---|---|---|
| Plemsi (anual) | $1.242.000 (≈ $52/doc) | $2.116.800 (≈ $35/doc) |
| MATIAS API (casa de software, por paquete) | 30.000 docs: $630.000 + firma digital desde $99.000/NIT/año (≈ $24/doc) | 50.000 docs: $850.000 + firma (≈ $19/doc) |
| Bilidox | Solo publica planes pequeños (100 docs/año: $60.000 ≈ $600/doc); a volumen, cotización | — |

The Factory HKA, Dataico, Alegra, Factus y Alanube **no publican precio**: hay que pedir cotización para 24.000 y 60.000 documentos al año, por NIT y como integrador.

## MATIAS API: barato, pero cambia la decisión 1
MATIAS no es proveedor tecnológico: cada comercio **se habilita ante la DIAN como facturador con software propio**, con su propio certificado de firma digital (desde $99.000 al año por NIT). MATIAS firma y transmite con ese certificado. Es lo más barato a volumen y soporta DE-POS y muchos NIT, pero:
- cada comercio hace su propia habilitación (set de pruebas) y es responsable ante la DIAN como software propio;
- dependemos de una empresa que no está en el listado de proveedores;
- contradice la decisión 1 del equipo (proveedor tecnológico), así que el equipo tendría que cambiarla a conciencia.

## Recomendación
1. **Pedir cotización y sandbox a The Factory HKA y a Dataico.** Son los dos que cumplen lo indispensable verificado: están en el listado oficial, tienen API documentada y emiten documentos equivalentes. HKA además documenta la contingencia tipo 03 con numeración del emisor, que es exactamente nuestro modelo de la T5. Pedir:
   - el endpoint de **DE-POS y nota de ajuste**, y si la respuesta trae **CUDE y QR de inmediato**;
   - cómo transmitir **contingencia** con nuestra numeración;
   - precio para **24.000 y 60.000 documentos al año**, por NIT y con programa para integradores (varios comercios);
   - si el set de pruebas de habilitación se hace en su sandbox.
2. **Alegra como tercera opción**, si confirma que su API emite DE-POS.
3. **Plemsi** solo si muestra su resolución de habilitación (o la del proveedor con el que opera): sus precios son claros y competitivos.
4. Dejar **MATIAS API** como plan B de costo, si el equipo decide cambiar a software propio.
5. Descartar por ahora **Factus** (su API no muestra DE-POS) y **Alanube** (no menciona DE-POS ni está verificado).

Con la respuesta de los proveedores se elige en una tabla final y se arranca la T7. El adaptador ya está listo: solo hay que escribir la clase del proveedor elegido (`Provider.send()`) y sus credenciales por variables de entorno.

## Fuentes
- DIAN, [proveedores tecnológicos autorizados](https://micrositios.dian.gov.co/sistema-de-facturacion-electronica/proveedores-tecnologicos/) ([listado en Excel](https://www.dian.gov.co/impuestos/factura-electronica/Documents/Proveedores-habilitados-15102026.xlsx)).
- The Factory HKA: [facturación electrónica](https://thefactoryhka.com.co/facturacion-electronica/), [sección de integración](https://felcowiki.thefactoryhka.com.co/index.php/Secci%C3%B3n_para_clientes_de_Integraci%C3%B3n), [preguntas frecuentes de integración (contingencia)](https://felcowiki.thefactoryhka.com.co/index.php/Preguntas_Frecuentes_de_Integraci%C3%B3n_con_servicio_Web_(Val._Previa)).
- Dataico: [API](https://facturaelectronica.dataico.com/api), [documentación de la API](https://portaldelcliente.dataico.com/es/knowledge/documentaci%C3%B3n-t%C3%A9cnica-de-la-api-de-dataico-factura-electr%C3%B3nica), [POS electrónico](https://portaldelcliente.dataico.com/es/knowledge/informaci%C3%B3n-sobre-pos-electr%C3%B3nico).
- Alegra: [API de facturación electrónica](https://www.alegra.com/colombia/api/facturacion-electronica/), [documentos POS electrónicos](https://ayuda.alegra.com/col/emite-documentos-equivalentes-pos-electronicos).
- Plemsi: [sitio](https://plemsi.com/) y [precios](https://plemsi.com/precios/).
- MATIAS API: [casas de software](https://matias-api.com/casas-de-software/), [documentación](https://docs.matias-api.com/).
- Factus: [sitio](https://www.factus.com.co/), [documentación](https://developers.factus.com.co/).
- Alanube: [Colombia](https://www.alanube.co/colombia/).
- Bilidox: [sitio](https://bilidox.com/).
