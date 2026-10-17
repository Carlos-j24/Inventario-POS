# Spec 005 — Facturación electrónica DIAN

> Estado: **decisiones cerradas por el equipo (2026-10-17)**; pendiente aprobar el PR para empezar a programar. Base normativa: Resolución DIAN 000165 de 2023 (compilada en la Resolución Única 000227 de 2025). Confirmar con el contador antes de aprobar.

## Problema
Hoy cada venta queda con un número interno (`V-000010`) que **no tiene validez fiscal**. Desde 2024 el tiquete POS debe ser un **documento equivalente electrónico** validado por la DIAN (calendario del art. 23, ya vencido para todos los grupos), y el cliente que lo pida debe recibir **factura electrónica**. Sin esto, la ferretería no puede usar el sistema en producción.

## Objetivo
Que cada venta genere su documento fiscal electrónico validado por la DIAN, que las devoluciones y anulaciones generen su nota, y que la caja siga vendiendo aunque se caiga internet o la DIAN, sin dejar de cumplir.

## Reglas de la DIAN que aplican (Res. 165 de 2023)
- **Documento equivalente electrónico POS (DE-POS):** puede expedirse sin importar el valor de la venta (art. 16, parágrafo); el tope de 5 UVT era del tiquete en papel. Solo se entiende expedido cuando la DIAN lo valida y se entrega al cliente, con la leyenda "Documento validado por la Dian" y código QR (art. 19).
- **Cliente:** si no da sus datos, se registra como *consumidor final* (`222222222222`), pero entonces el documento no le sirve para IVA descontable ni para costos y deducciones (art. 19, parágrafo 1). Si los da (nombre o razón social y número de identificación), sí le sirve.
- **Factura electrónica (FE):** se expide cuando el cliente la pide (art. 16, parágrafo transitorio). Exige más datos del cliente y se le entrega por correo (XML + representación gráfica) si es facturador (art. 35).
- **Anulaciones y devoluciones:** la **nota crédito** anula o ajusta una FE (art. 36) y la **nota de ajuste** anula o corrige un DE-POS (art. 22). Un número anulado no se reutiliza.
- **Numeración:** autorizada por la DIAN con prefijo (hasta 4 caracteres), rango y vigencia máxima de 2 años; prefijo distinto como mínimo por establecimiento o punto de venta (arts. 42–48). Hay que pedir la nueva antes de que se agote o venza.
- **Contingencia (art. 37):**
  - Si falla el sistema del vendedor (sin internet): se emite el documento en físico y, superado el problema, se genera el XML y se transmite **dentro de 48 horas**.
  - Si falla la DIAN: se expide sin validación previa y se transmite dentro de 48 horas desde que se restablece.
  - Si se agota la numeración durante la contingencia: numeración autónoma y luego se informa (art. 42).
- **Entrega al cliente que no es facturador:** basta la representación gráfica impresa; es el medio por defecto si el cliente no indica otro (art. 35, 2.3 y 2.5).

## Lo que cambia
- **Documento fiscal por venta:** cada venta (y cada devolución o anulación) tiene un documento con tipo (DE-POS, FE, nota de ajuste, nota crédito), prefijo y consecutivo autorizados, CUDE/CUFE, QR, estado (`pendiente`, `enviado`, `validado`, `rechazado`, `contingencia`) e historial de envíos y errores. El número interno `V-…` se conserva para uso interno.
- **Numeración por caja:** cada caja tiene su resolución de numeración (número, fecha, prefijo, rango y vigencia) y avisa cuando quedan pocos números o se acerca el vencimiento.
- **Clientes:** catálogo de clientes (tipo y número de documento con dígito de verificación, nombre o razón social, correo, responsabilidades fiscales). En caja: *consumidor final* por defecto y búsqueda o alta rápida cuando el cliente da sus datos o pide factura.
- **Envío asíncrono:** la venta no espera a la DIAN. Una cola en el servidor envía los documentos con reintentos; la caja ve el estado y el supervisor tiene una bandeja de rechazados y pendientes.
- **Tiquete impreso:** representación gráfica para impresora térmica de 80 mm (desde el navegador) con los datos del art. 19 y el QR; si el cliente da correo, también se le envía.
- **Impuestos:** separar **exento** de **excluido** en el catálogo (hoy "0 %" se rotula "Exento"); la DIAN los reporta distinto.
- **Integración intercambiable:** un adaptador con una sola interfaz (emitir, consultar estado, emitir nota). En desarrollo y en los tests se usa un proveedor simulado; en producción, el que elija el equipo.

## Fuera de esta spec
Ventas a crédito y eventos RADIAN (acuse y aceptación), documento soporte de compras a no obligados, nómina electrónica, retenciones (ReteIVA, ReteICA, ReteFuente) y facturación de otros tipos de negocio (droguería, supermercado).

## Riesgos y puntos a confirmar con el contador o el proveedor
- Si una **devolución parcial** de un DE-POS se hace con nota de ajuste (el art. 22 habla de "anulación o corrección") o si conviene otro mecanismo.
- Los códigos exactos de contingencia (tipo 3 y tipo 4) y su manejo los define el anexo técnico y, en la práctica, el proveedor.
- Responsabilidades fiscales de la ferretería (régimen, gran contribuyente, autorretenedor) para el encabezado de los documentos.
- Los números de contingencia que un equipo reservó y no usó (por ejemplo, si se daña) quedan sin usar: confirmar si hay que informarlos a la DIAN.

## Criterios de aceptación (propuestos)
- Una venta en línea queda con un DE-POS validado (CUDE y QR) en segundos, sin hacer esperar a la caja.
- Una venta para un cliente que pide factura queda con FE validada y se le envía al correo.
- Anular una venta genera su nota (de ajuste o crédito) validada; una devolución parcial genera la nota por el valor devuelto.
- Sin conexión, la caja vende y entrega tiquete de contingencia; al volver la conexión, todo se transmite y valida dentro de 48 horas, y el supervisor ve si algo quedó pendiente.
- La numeración nunca se repite ni salta números, ni siquiera con dos cajas vendiendo a la vez.
- Ningún documento sale con una resolución vencida o fuera de rango; la caja avisa antes de que se agote.
- Las credenciales del proveedor y el certificado viven en variables de entorno, nunca en el repositorio.

## Decisiones (equipo, 2026-10-17)
1. **Proveedor tecnológico autorizado, por API.** El proveedor firma, arma el XML UBL y valida con la DIAN. Nuestro código habla con un adaptador de una sola interfaz, así que cambiar de proveedor es cambiar el adaptador. Cuál proveedor es una decisión comercial pendiente (cotizar costo por documento, soporte de DE-POS y de contingencia, y API).
2. **DE-POS a consumidor final por defecto; factura electrónica solo si el cliente la pide** y da sus datos. El cliente también puede dar sus datos en un DE-POS para descontar el IVA.
3. **Contingencia sin conexión:** la caja sigue vendiendo, imprime el tiquete de contingencia con numeración de la caja y el servidor transmite a la DIAN al volver la conexión, dentro del plazo de 48 horas.
4. **Tiquete impreso de 80 mm con QR** desde el navegador, y correo opcional si el cliente lo da.
