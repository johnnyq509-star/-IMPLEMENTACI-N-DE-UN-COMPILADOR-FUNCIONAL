# Compilador Mini-Lang en Python

**Compiladores — Proyecto Final**  
Universidad Metropolitana de Educación, Ciencia y Tecnología  
Licenciatura en Sistemas y Programación  
Estudiante: **Johnny Quezada** · Profesor: **Martin Humberto Coronado Gutiérrez**

---

## Descripción

Este proyecto implementa un **compilador completo de cuatro fases** para un lenguaje imperativo simplificado llamado **Mini-Lang**, escrito íntegramente en Python 3 sin dependencias externas. El compilador toma código fuente como texto y lo procesa a través de análisis léxico, sintáctico, semántico y generación de código intermedio, reportando errores descriptivos en cada etapa.

El objetivo es demostrar de forma práctica cómo funciona internamente un compilador real: desde leer caracteres crudos del fuente hasta producir una representación independiente de la máquina lista para optimización o ejecución.

---

## Lenguaje soportado (Mini-Lang)

```
// Declaración de variables
int a = 10;
float pi = 3.14;
string nombre = "hola";

// Asignación
a = a + 1;

// Condicional
if (a > 5) {
    print(a);
} else {
    print(0);
}

// Bucle
while (a < 100) {
    a = a * 2;
}

// Impresión y retorno
print(a);
return a;
```

### Tipos de datos
| Tipo     | Ejemplo       |
|----------|---------------|
| `int`    | `42`, `0`     |
| `float`  | `3.14`, `0.5` |
| `string` | `"texto"`     |
| `bool`   | `true`, `false` |

### Operadores
| Categoría    | Símbolos                          |
|--------------|-----------------------------------|
| Aritméticos  | `+`  `-`  `*`  `/`               |
| Comparación  | `>`  `<`  `>=`  `<=`  `==`  `!=` |
| Asignación   | `=`                               |

---

## Estructura del proyecto

```
compilador/
├── compilador.py   # Código fuente principal (todas las fases)
└── README.md       # Este archivo
```

---

## Fases del compilador

### Fase 1 — Análisis Léxico (`analizar_lexico`)

Convierte el código fuente en una secuencia de **tokens** usando expresiones regulares compiladas en un patrón maestro. Cada token incluye su tipo, valor, número de línea y columna.

**Tokens reconocidos:** `INT`, `FLOAT`, `STRING`, `ID`, `RESERVADA`, `OP_COMP`, `OP_ARIT`, `ASSIGN`, `LPAREN`, `RPAREN`, `LBRACE`, `RBRACE`, `PUNTO_COMA`, `COMA`.

Los errores léxicos (caracteres no reconocidos) se recopilan sin detener el análisis gracias al patrón `MISMATCH`, que actúa como "red de seguridad" al final de la especificación.

### Fase 2 — Análisis Sintáctico (`Parser`)

Implementa un **parser recursivo descendente LL** donde cada método corresponde a una regla de la gramática. Construye el **Árbol de Sintaxis Abstracta (AST)** compuesto por nodos `Nodo(tipo, hijos, valor, linea)`.

La precedencia de operadores está codificada en la jerarquía de la gramática: `comparacion → suma → termino → factor`, de modo que `*` y `/` se ubican más profundo en el árbol que `+` y `-`, garantizando evaluación correcta.

### Fase 3 — Análisis Semántico (`AnalizadorSemantico` + `TablaSimbolos`)

Recorre el AST verificando:
- **Declaración antes de uso**: toda variable debe declararse con `int`, `float`, etc. antes de ser referenciada.
- **Compatibilidad de tipos**: no se puede asignar `string` a una variable `int`. Se permite promoción implícita `int → float`.
- **Inicialización**: una variable no puede usarse antes de recibir un valor.
- **Ámbitos anidados**: los bloques `if` y `while` abren y cierran su propio ámbito, permitiendo shadowing de variables locales.

La `TablaSimbolos` usa una pila de diccionarios para gestionar los ámbitos.

### Fase 4 — Generación de Código Intermedio (`GeneradorCodigo`)

Produce **código de tres direcciones (TAC)** donde cada instrucción tiene la forma `result = op1 operador op2`. Los temporales se nombran `t0, t1, t2, …` y las etiquetas de salto `L0, L1, L2, …`.

Ejemplo para `if (y > 20) { x = x + 1; } else { print(y); }`:
```
t0 = y > 20
if t0 goto L0
goto L2
L0:
  t1 = x + 1
  x = t1
  goto L1
L2:
  print y
L1:
```

### Manejo de errores

Los errores se clasifican en tres tipos con jerarquía de herencia:

| Clase          | Cuándo se lanza                                       |
|----------------|-------------------------------------------------------|
| `LexError`     | Carácter no perteneciente al alfabeto del lenguaje    |
| `SyntaxErr`    | Construcción gramaticalmente inválida                  |
| `SemanticError`| Variable no declarada, tipo incompatible, etc.        |

Todos incluyen número de línea y descripción del problema. Los errores semánticos son **no fatales**: se recopilan y se reportan todos al final sin interrumpir el análisis.

---

## Cómo ejecutar

```bash
# Requiere Python 3.8+, sin dependencias externas
python compilador.py
```

El archivo incluye **6 casos de prueba** que cubren:
1. Expresiones aritméticas con precedencia correcta
2. Condicional `if / else` con TAC completo
3. Bucle `while` con acumulador
4. Error semántico: variable no declarada
5. Error semántico: tipo incompatible (`int` ← `string`)
6. Error léxico: carácter inválido (`@`)

Para compilar tu propio código, usa la función `compilar()`:

```python
from compilador import compilar

compilar("""
int x = 10;
int y = x * 2 + 5;
if (y > 20) {
    print(y);
}
""", nombre="Mi programa")
```

---

## Ejemplo de salida completa

```
══════════════════════════════════════════════════════════════
  Compilando: Prueba 1 — Expresiones aritméticas
══════════════════════════════════════════════════════════════

FASE 1 — TOKENS
  Token(RESERVADA    | val='int'  | línea=1, col=1)
  Token(ID           | val='a'    | línea=1, col=5)
  ...

FASE 2 — AST
└── PROGRAM
    ├── DECL
    │   ├── TIPO(int)
    │   ├── ID(a)
    │   └── NUM_INT(10)
    └── ...

TABLA DE SÍMBOLOS
  Nombre   Tipo   Valor   Línea
  a        int    10      1
  b        int    32      2

CÓDIGO DE TRES DIRECCIONES (TAC)
    0│ a = 10    // decl int
    1│ t0 = a * 3
    2│ t1 = t0 + 2
    3│ b = t1    // decl int
    4│ print b

✅ Compilación exitosa.
```

---

## Tecnologías

- **Lenguaje:** Python 3.8+
- **Módulos usados:** `re` (expresiones regulares), `typing` (type hints)
- **Sin dependencias externas** — solo biblioteca estándar de Python

---

## Autor

**Johnny Quezada**  
Licenciatura en Sistemas y Programación  
Universidad Metropolitana de Educación, Ciencia y Tecnología  
Compiladores · Prof. Martin Humberto Coronado Gutiérrez · 2026
