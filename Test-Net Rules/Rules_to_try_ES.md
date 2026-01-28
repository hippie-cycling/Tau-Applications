# Reglas a probar

**Ejemplo 1: El receptor recibe el total -1 (impuesto)**

`always (o1\[t\] = i1\[t\] - { 1 }:bv\[64\])`

*Siempre, el output final (o1) será igual a la cantidad de Agoras a enviar (input 1 i1) - 1.*

---

**Ejemplo 2: El receptor recibe el total más un bonus de +10**

`always (o1\[t\] = i1\[t\] + { 10 }:bv\[64\])`

*Siempre, el output final (o1) será igual a la cantidad de Agoras a enviar (i1\[t\]) +1*

---

**Ejemplo 3: Solo se pueden mandar un valor concreto de Agoras (66 en este caso)** 

`always ( (i1\[t\]:bv\[64\] = { 66 }:bv\[64\]) ? o4\[t\] = { #b1 }:bv\[1\] : o4\[t\] = { #b0 }:bv\[1\] )`

*Siempre, si cantidad de Agoras es 66. Si es cierto, tau responde 1. De lo contrario 0.*

---

**Ejemplo 4: Limitar la cantidad máxima de Agoras a transferir.**

`always ( (i1\[t\]:bv\[64\] > { 100 }:bv\[64\]) ? o1\[t\] = { 100 }:bv\[64\] : o1\[t\] = i1\[t\]:bv\[64\] )`

*Siempre, si la cantidad de Agoras es mayor a 100. Si es cierto, se mandan 100. De lo contrario, lo que el usuario mande.*

---

**Ejemplo 5: Regla computacionalmente cara**

*Los solucionadores SMT son rápidos en la suma (+) y la lógica bit a bit (&, |, ^), pero son notoriamente lentos en la multiplicación y la división combinadas. Esto es computacionalmente costoso (comportamiento NP-difícil).*

`always ( o1\[t\] = ( (i1\[t\] \* i1\[t\]) \* { 123456789 }:bv\[64\] ) / { 987654321 }:bv\[64\] )`

---

**Regla 6: Regla de Schrödinger**

Esto pone a prueba el sistema de revisión puntual. Se proporciona una regla que es lógicamente imposible de cumplir en un solo momento.

`always ( o1\[t\] = i1\[t\]:bv\[64\] && o1\[t\] != i1\[t\]:bv\[64\] )`

*establecer que el resultado debe ser igual a la entrada Y no igual a la entrada al mismo tiempo. Tau debería detectarlo.*
