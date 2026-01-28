# 📓Guía para entender cómo funcionan las reglas en la Tau test-net

## Background

La Tau test-net permite realizar transacciones entre dos direcciones al igual que una blockchain convencional, pero lo que la diferencia de las demás, és que además tiene la particularidad de que se pueden introducir reglas. Estas reglas son las que gobiernan como la test-net procesa las transacciones.

Estas reglas pueden modificarse bloque a bloque, creando una blockchain dinámica, cuya gobernanza es flexible a lo largo del tiempo.

Por ejemplo, en el bloque #10 hay una colección de reglas que permite a cualquiera enviar cualquier cantidad de Agoras siempre y cuando no supere el balance de la cartera. Sin embargo, Pepito decide que para el bloque #11, se va a introducir nueva regla que va a restringir futuras transacciones a únicamente 66 Agoras, ni menos ni más. 

Pepito puede realizar una transacción en la que introduce dicha nueva regla, por lo que, si es aceptada, el bloque #11 ahora contiene una nueva condición, que para poder procesar el bloque #12, Pepito y el resto solo pueden mandar 66 Agoras, cualquier otra cantidad es rechazada por Tau.

¿Cómo se implementa esto? Gracias a Tau, cada bloque se verifica acorde a las reglas presentes. Tau verifica que la nueva transacción cumple todas las reglas y decide si la transacción es válida o no.

Existen una colección de reglas básicas que gobiernan la test-net en su inicio. Estas son:

- **Regla para detectar fondos insuficientes**
- **Regla para verificar que la dirección de envío es distinta a la de recepción**
- **Regla para verificar si la cantidad a enviar es 0**
- **Regla para detectar inputs inválidos**

## Ejemplo

### ¿Cómo se define una regla? La regla para detectar fondos insuficientes

Lógica: Si el valor a transferir es mayor al balance, Tau debe responder falso (0) y la transacción se debe rechazar. De lo contrario, Tau debe responde verdadero (1) y la transacción ser aceptada.

En este caso se usa un operador ternario, la sintaxis en lenguaje Tau se define así: *Nota: Tau-Lang esta en fase alpha, la sintaxis puede cambiar en el futuro.*

>**(** Condición **?** Accion_si_verdadero **:** Accion_si_falso **)**

La regla que comentamos aquí escrita en lenguaje Tau como operador ternario es:

>always **(**(i1\[t\] : bv\[64\] > i2\[t\]) **?** o2\[t\] = { #b0 }:bv\[1\] **:** o2\[t\] = { #b1 }:bv\[1\]**)**.

*Traducción: Siempre, si i1\[t\] es mayor que i2\[t\] **:** Si es cierto responde 1, de lo contrario 0.*

¿Qué significa cada input y output de esta regla?

Streams de entrada: Valores de entrada a Tau.

> **i1\[t\]: Cantidad a enviar (bitvector de 64 bits)**

> **i2\[t\]: Balance del que envía (bitvector de 64 bits)**

Streams de salida: Valores que Tau responde.

> **o2\[t\]: validación (0 o 1). Si es 1 la regla es válida y se acepta la transacción, si es 0 se rechaza.**

---

**En general:**

| **Stream** | **Type** | **Name** | **Description** |
| --- | --- | --- | --- |
| **i0\[t\]** | tau | **Rule Proposal** | Used for submitting new Tau code to update the blockchain's rules (via Pointwise Revision). |
| **i1\[t\]** | bv\[64\] | **Transfer Amount** | The quantity of coins the sender _wants_ to transfer in the current transaction. |
| **i2\[t\]** | bv\[64\] | **Sender Balance** | The current wallet balance of the sender _before_ the transaction is processed. |
| **i3\[t\]** | bv\[64\] | **Source Address** | The unique ID (address) of the person sending the coins. |
| **i4\[t\]** | bv\[64\] | **Dest. Address** | The unique ID (address) of the person receiving the coins. |

| **Stream** | **Type** | **Role** | **What it means** |
| --- | --- | --- | --- |
| **o1\[t\]** | **Data** | **The Final Amount** | "We are moving **X** coins." |
| **o2\[t\]** | **Flag** | **Funds Check** | "Does the sender have enough money?" (1 = Yes, 0 = No) |
| **o3\[t\]** | **Flag** | **Address Check** | "Are Sender and Receiver different people?" (1 = Yes, 0 = No) |
| **o4\[t\]** | **Flag** | **Logic Check** | "Is the amount valid (e.g., not zero)?" (1 = Yes, 0 = No) |

---
