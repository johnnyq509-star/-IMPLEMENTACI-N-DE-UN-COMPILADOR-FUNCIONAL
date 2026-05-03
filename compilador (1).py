"""
=============================================================
  COMPILADORES — Proyecto Final
  Compilador Mini-Lang en Python
  Prof. Martin Humberto Coronado Gutiérrez
  Estudiante: Johnny Quezada
=============================================================

  Fases implementadas:
    1. Análisis Léxico      — tokenización con manejo de errores
    2. Análisis Sintáctico  — Parser recursivo descendente (LL)
                              con construcción de AST
    3. Análisis Semántico   — verificación de tipos y tabla de
                              símbolos
    4. Generación de Código — código de tres direcciones (TAC)
    5. Manejo de Errores    — mensajes con línea y tipo de error

  Lenguaje soportado (Mini-Lang):
    - Declaración:  int x = expr;
    - Asignación:   x = expr;
    - Condicional:  if (cond) { ... } else { ... }
    - Bucle:        while (cond) { ... }
    - Impresión:    print(expr);
    - Expresiones:  +  -  *  /  con precedencia correcta
    - Comparación:  >  <  >=  <=  ==  !=
=============================================================
"""

import re
import sys
from typing import List, Optional, Tuple, Dict

# ═════════════════════════════════════════════════════════════
# UTILIDADES GLOBALES
# ═════════════════════════════════════════════════════════════

class CompilerError(Exception):
    """Error base del compilador con información de línea."""
    def __init__(self, mensaje: str, linea: int = 0, tipo: str = "Error"):
        self.mensaje = mensaje
        self.linea   = linea
        self.tipo    = tipo
        super().__init__(self.__str__())

    def __str__(self):
        return f"[{self.tipo}] Línea {self.linea}: {self.mensaje}"


class LexError(CompilerError):
    def __init__(self, msg, linea):
        super().__init__(msg, linea, "Error Léxico")

class SyntaxErr(CompilerError):
    def __init__(self, msg, linea):
        super().__init__(msg, linea, "Error Sintáctico")

class SemanticError(CompilerError):
    def __init__(self, msg, linea):
        super().__init__(msg, linea, "Error Semántico")


# ═════════════════════════════════════════════════════════════
# FASE 1 — ANÁLISIS LÉXICO
# ═════════════════════════════════════════════════════════════

# Palabras reservadas del lenguaje Mini-Lang
PALABRAS_RESERVADAS = {
    "int", "float", "string", "bool",
    "if", "else", "while",
    "print", "return", "true", "false"
}

# Especificación de tokens: (nombre, patrón_regex)
# El ORDEN es importante: patrones más específicos primero.
ESPECIFICACION_TOKENS = [
    # Literales numéricos (FLOAT antes que INT)
    ("FLOAT",      r'\d+\.\d+'),
    ("INT",        r'\d+'),

    # Literales de cadena
    ("STRING",     r'"[^"\n]*"'),

    # Identificadores y palabras reservadas
    ("ID",         r'[a-zA-Z_][a-zA-Z0-9_]*'),

    # Operadores de comparación (dos caracteres antes que uno)
    ("OP_COMP",    r'>=|<=|==|!=|>|<'),

    # Operadores aritméticos
    ("OP_ARIT",    r'[+\-*/]'),

    # Asignación
    ("ASSIGN",     r'='),

    # Delimitadores
    ("LPAREN",     r'\('),
    ("RPAREN",     r'\)'),
    ("LBRACE",     r'\{'),
    ("RBRACE",     r'\}'),
    ("PUNTO_COMA", r';'),
    ("COMA",       r','),

    # Ignorados
    ("COMENTARIO", r'//[^\n]*'),         # comentario de línea
    ("NEWLINE",    r'\n'),
    ("ESPACIO",    r'[ \t\r]+'),

    # Carácter no reconocido (siempre al final)
    ("MISMATCH",   r'.'),
]

PATRON_MAESTRO = re.compile(
    "|".join(f"(?P<{nombre}>{patron})"
             for nombre, patron in ESPECIFICACION_TOKENS)
)


class Token:
    """Unidad léxica producida por el lexer."""

    __slots__ = ("tipo", "valor", "linea", "columna")

    def __init__(self, tipo: str, valor: str, linea: int, columna: int):
        self.tipo    = tipo
        self.valor   = valor
        self.linea   = linea
        self.columna = columna

    def __repr__(self):
        return (f"Token({self.tipo:<12} | val={self.valor!r:<15} "
                f"| línea={self.linea}, col={self.columna})")


def analizar_lexico(codigo: str) -> Tuple[List[Token], List[CompilerError]]:
    """
    Fase 1 — Análisis Léxico.

    Recorre el código fuente y produce una lista de tokens.
    Los errores léxicos se recopilan sin detener el análisis
    (estrategia de recuperación a nivel de carácter).

    Retorna:
        tokens : lista de Token válidos
        errores: lista de LexError encontrados
    """
    tokens:  List[Token]         = []
    errores: List[CompilerError] = []
    linea        = 1
    inicio_linea = 0

    for m in PATRON_MAESTRO.finditer(codigo):
        tipo    = m.lastgroup
        valor   = m.group()
        columna = m.start() - inicio_linea + 1

        # ── Ignorar espacios y comentarios ───────────────────
        if tipo in ("ESPACIO", "COMENTARIO"):
            continue

        if tipo == "NEWLINE":
            linea       += 1
            inicio_linea = m.end()
            continue

        # ── Carácter no reconocido → error léxico ────────────
        if tipo == "MISMATCH":
            errores.append(
                LexError(f"Carácter no reconocido: '{valor}'", linea)
            )
            continue

        # ── Reclasificar identificadores como reservadas ─────
        if tipo == "ID" and valor in PALABRAS_RESERVADAS:
            tipo = "RESERVADA"

        tokens.append(Token(tipo, valor, linea, columna))

    # Centinela de fin de archivo
    tokens.append(Token("EOF", "", linea, 0))
    return tokens, errores


# ═════════════════════════════════════════════════════════════
# FASE 2 — ANÁLISIS SINTÁCTICO (Parser LL recursivo descendente)
# ═════════════════════════════════════════════════════════════

class Nodo:
    """
    Nodo del Árbol de Sintaxis Abstracta (AST).

    Atributos:
        tipo   : etiqueta del nodo ("DECL", "ADD", "IF", …)
        hijos  : lista de nodos hijo
        valor  : dato literal para hojas (NUM, ID, etc.)
        linea  : número de línea en el fuente (para errores semánticos)
    """

    def __init__(self, tipo: str,
                 hijos: Optional[List["Nodo"]] = None,
                 valor=None,
                 linea: int = 0):
        self.tipo  = tipo
        self.hijos = hijos or []
        self.valor = valor
        self.linea = linea

    def __repr__(self):
        if self.valor is not None:
            return f"Nodo({self.tipo}, val={self.valor})"
        return f"Nodo({self.tipo}, hijos={len(self.hijos)})"


def imprimir_ast(nodo: Nodo, prefijo: str = "", es_ultimo: bool = True) -> None:
    """Imprime el AST como árbol visual en la consola."""
    conector  = "└── " if es_ultimo else "├── "
    extension = "    " if es_ultimo else "│   "
    etiqueta  = (f"{nodo.tipo}({nodo.valor})"
                 if nodo.valor is not None else nodo.tipo)
    print(prefijo + conector + etiqueta)
    for i, hijo in enumerate(nodo.hijos):
        imprimir_ast(hijo, prefijo + extension, i == len(nodo.hijos) - 1)


class Parser:
    """
    Fase 2 — Análisis Sintáctico.

    Implementa un parser recursivo descendente (LL).
    Cada método corresponde a una regla de la gramática:

      programa    → sentencia*
      sentencia   → declaracion | asignacion | condicional
                  | mientras   | print_stmt  | retorno
      declaracion → tipo ID '=' expr ';'
      asignacion  → ID '=' expr ';'
      condicional → 'if' '(' expr ')' bloque ('else' bloque)?
      mientras    → 'while' '(' expr ')' bloque
      print_stmt  → 'print' '(' expr ')' ';'
      retorno     → 'return' expr ';'
      bloque      → '{' sentencia* '}'
      expr        → comparacion
      comparacion → suma (OP_COMP suma)*
      suma        → termino (('+' | '-') termino)*
      termino     → factor (('*' | '/') factor)*
      factor      → NUM | FLOAT | STRING | BOOL | ID | '(' expr ')'
    """

    TIPOS = {"int", "float", "string", "bool"}

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos    = 0

    # ── Utilidades ──────────────────────────────────────────

    def _actual(self) -> Token:
        return self.tokens[self.pos]

    def _consumir(self, tipo_esperado: Optional[str] = None) -> Token:
        tok = self._actual()
        if tipo_esperado and tok.tipo != tipo_esperado:
            raise SyntaxErr(
                f"Se esperaba '{tipo_esperado}' "
                f"pero se encontró '{tok.tipo}' ('{tok.valor}')",
                tok.linea
            )
        self.pos += 1
        return tok

    def _ver(self, tipo: str) -> bool:
        return self._actual().tipo == tipo

    def _ver_valor(self, valor: str) -> bool:
        return self._actual().valor == valor

    def _es_tipo(self) -> bool:
        return (self._actual().tipo == "RESERVADA"
                and self._actual().valor in self.TIPOS)

    # ── Punto de entrada ────────────────────────────────────

    def parsear(self) -> Nodo:
        """Construye el nodo raíz PROGRAM."""
        sentencias = []
        while not self._ver("EOF"):
            sentencias.append(self._sentencia())
        return Nodo("PROGRAM", sentencias, linea=1)

    # ── Sentencias ──────────────────────────────────────────

    def _sentencia(self) -> Nodo:
        tok = self._actual()

        if self._es_tipo():
            return self._declaracion()

        if tok.tipo == "RESERVADA":
            if tok.valor == "if":
                return self._condicional()
            if tok.valor == "while":
                return self._mientras()
            if tok.valor == "print":
                return self._print_stmt()
            if tok.valor == "return":
                return self._retorno()

        if tok.tipo == "ID":
            return self._asignacion()

        raise SyntaxErr(
            f"Sentencia inesperada: '{tok.valor}'", tok.linea
        )

    def _declaracion(self) -> Nodo:
        """tipo ID = expr ;"""
        tipo_tok = self._consumir("RESERVADA")
        id_tok   = self._consumir("ID")
        self._consumir("ASSIGN")
        expr = self._expr()
        self._consumir("PUNTO_COMA")
        return Nodo("DECL", [
            Nodo("TIPO", valor=tipo_tok.valor, linea=tipo_tok.linea),
            Nodo("ID",   valor=id_tok.valor,   linea=id_tok.linea),
            expr
        ], linea=tipo_tok.linea)

    def _asignacion(self) -> Nodo:
        """ID = expr ;"""
        id_tok = self._consumir("ID")
        self._consumir("ASSIGN")
        expr = self._expr()
        self._consumir("PUNTO_COMA")
        return Nodo("ASSIGN", [
            Nodo("ID", valor=id_tok.valor, linea=id_tok.linea),
            expr
        ], linea=id_tok.linea)

    def _condicional(self) -> Nodo:
        """if ( expr ) bloque [ else bloque ]"""
        linea = self._actual().linea
        self._consumir("RESERVADA")   # if
        self._consumir("LPAREN")
        condicion = self._expr()
        self._consumir("RPAREN")
        cuerpo_if = self._bloque()
        hijos = [condicion, cuerpo_if]
        if (self._ver("RESERVADA") and self._ver_valor("else")):
            self._consumir("RESERVADA")
            hijos.append(self._bloque())
        return Nodo("IF", hijos, linea=linea)

    def _mientras(self) -> Nodo:
        """while ( expr ) bloque"""
        linea = self._actual().linea
        self._consumir("RESERVADA")   # while
        self._consumir("LPAREN")
        condicion = self._expr()
        self._consumir("RPAREN")
        cuerpo = self._bloque()
        return Nodo("WHILE", [condicion, cuerpo], linea=linea)

    def _print_stmt(self) -> Nodo:
        """print ( expr ) ;"""
        linea = self._actual().linea
        self._consumir("RESERVADA")   # print
        self._consumir("LPAREN")
        expr = self._expr()
        self._consumir("RPAREN")
        self._consumir("PUNTO_COMA")
        return Nodo("PRINT", [expr], linea=linea)

    def _retorno(self) -> Nodo:
        """return expr ;"""
        linea = self._actual().linea
        self._consumir("RESERVADA")   # return
        expr = self._expr()
        self._consumir("PUNTO_COMA")
        return Nodo("RETURN", [expr], linea=linea)

    def _bloque(self) -> Nodo:
        """{ sentencia* }"""
        linea = self._actual().linea
        self._consumir("LBRACE")
        sentencias = []
        while not self._ver("RBRACE") and not self._ver("EOF"):
            sentencias.append(self._sentencia())
        self._consumir("RBRACE")
        return Nodo("BLOCK", sentencias, linea=linea)

    # ── Expresiones (precedencia de operadores) ─────────────

    def _expr(self) -> Nodo:
        return self._comparacion()

    def _comparacion(self) -> Nodo:
        izq = self._suma()
        while self._ver("OP_COMP"):
            op  = self._consumir("OP_COMP")
            der = self._suma()
            izq = Nodo(f"CMP_{op.valor}", [izq, der], linea=op.linea)
        return izq

    def _suma(self) -> Nodo:
        izq = self._termino()
        while self._ver("OP_ARIT") and self._actual().valor in ("+", "-"):
            op  = self._consumir("OP_ARIT")
            der = self._termino()
            nodo_tipo = "ADD" if op.valor == "+" else "SUB"
            izq = Nodo(nodo_tipo, [izq, der], linea=op.linea)
        return izq

    def _termino(self) -> Nodo:
        izq = self._factor()
        while self._ver("OP_ARIT") and self._actual().valor in ("*", "/"):
            op  = self._consumir("OP_ARIT")
            der = self._factor()
            nodo_tipo = "MUL" if op.valor == "*" else "DIV"
            izq = Nodo(nodo_tipo, [izq, der], linea=op.linea)
        return izq

    def _factor(self) -> Nodo:
        tok = self._actual()

        if tok.tipo == "INT":
            self._consumir()
            return Nodo("NUM_INT", valor=int(tok.valor), linea=tok.linea)

        if tok.tipo == "FLOAT":
            self._consumir()
            return Nodo("NUM_FLOAT", valor=float(tok.valor), linea=tok.linea)

        if tok.tipo == "STRING":
            self._consumir()
            return Nodo("STR", valor=tok.valor.strip('"'), linea=tok.linea)

        if tok.tipo == "RESERVADA" and tok.valor in ("true", "false"):
            self._consumir()
            return Nodo("BOOL", valor=(tok.valor == "true"), linea=tok.linea)

        if tok.tipo == "ID":
            self._consumir()
            return Nodo("ID", valor=tok.valor, linea=tok.linea)

        if tok.tipo == "LPAREN":
            self._consumir("LPAREN")
            nodo = self._expr()
            self._consumir("RPAREN")
            return nodo

        raise SyntaxErr(
            f"Factor inesperado: '{tok.valor}' (tipo={tok.tipo})", tok.linea
        )


# ═════════════════════════════════════════════════════════════
# FASE 3 — ANÁLISIS SEMÁNTICO
# ═════════════════════════════════════════════════════════════

class EntradaSimbolo:
    """Registro de una variable en la tabla de símbolos."""
    __slots__ = ("nombre", "tipo", "valor", "linea", "inicializada")

    def __init__(self, nombre, tipo, valor=None, linea=0):
        self.nombre       = nombre
        self.tipo         = tipo
        self.valor        = valor
        self.linea        = linea
        self.inicializada = valor is not None

    def __repr__(self):
        return (f"EntradaSimbolo(nombre={self.nombre!r}, tipo={self.tipo}, "
                f"valor={self.valor}, línea={self.linea})")


class TablaSimbolos:
    """
    Tabla de símbolos con soporte de ámbitos (scopes) anidados.

    Cada nivel de ámbito es un diccionario independiente.
    La búsqueda sube por la pila hasta encontrar la declaración.
    """

    def __init__(self):
        self._ambitos: List[Dict[str, EntradaSimbolo]] = [{}]

    # ── Gestión de ámbitos ───────────────────────────────────

    def entrar_ambito(self):
        self._ambitos.append({})

    def salir_ambito(self):
        if len(self._ambitos) > 1:
            self._ambitos.pop()

    def _ambito_actual(self) -> Dict:
        return self._ambitos[-1]

    # ── Operaciones ─────────────────────────────────────────

    def declarar(self, nombre: str, tipo: str,
                 valor=None, linea: int = 0) -> None:
        if nombre in self._ambito_actual():
            raise SemanticError(
                f"Variable '{nombre}' ya fue declarada en este ámbito.",
                linea
            )
        self._ambito_actual()[nombre] = EntradaSimbolo(
            nombre, tipo, valor, linea
        )

    def asignar(self, nombre: str, valor, linea: int = 0) -> None:
        for ambito in reversed(self._ambitos):
            if nombre in ambito:
                ambito[nombre].valor        = valor
                ambito[nombre].inicializada = True
                return
        raise SemanticError(f"Variable '{nombre}' no declarada.", linea)

    def obtener(self, nombre: str, linea: int = 0) -> EntradaSimbolo:
        for ambito in reversed(self._ambitos):
            if nombre in ambito:
                return ambito[nombre]
        raise SemanticError(f"Variable '{nombre}' no declarada.", linea)

    def obtener_valor(self, nombre: str, linea: int = 0):
        entrada = self.obtener(nombre, linea)
        if not entrada.inicializada:
            raise SemanticError(
                f"Variable '{nombre}' usada antes de ser inicializada.", linea
            )
        return entrada.valor

    def imprimir(self) -> None:
        sep = "─" * 62
        print(f"\n{sep}")
        print(f"  {'TABLA DE SÍMBOLOS':^58}")
        print(sep)
        print(f"  {'Nombre':<14} {'Tipo':<10} {'Valor':<20} {'Línea'}")
        print(sep)
        for ambito in self._ambitos:
            for entrada in ambito.values():
                print(f"  {entrada.nombre:<14} {entrada.tipo:<10} "
                      f"{str(entrada.valor):<20} {entrada.linea}")
        print(sep)


# Mapa de compatibilidad de tipos para operaciones aritméticas
TIPOS_ARIT = {
    ("int",   "int"):   "int",
    ("float", "float"): "float",
    ("int",   "float"): "float",
    ("float", "int"):   "float",
}


class AnalizadorSemantico:
    """
    Fase 3 — Análisis Semántico.

    Recorre el AST en postorden, verifica tipos y llena
    la tabla de símbolos. Retorna el tipo inferido de cada
    subexpresión.
    """

    OPS_CMP = {"CMP_>", "CMP_<", "CMP_>=", "CMP_<=", "CMP_==", "CMP_!="}

    def __init__(self):
        self.tabla   = TablaSimbolos()
        self.errores: List[CompilerError] = []

    # ── Despacho principal ───────────────────────────────────

    def analizar(self, nodo: Nodo) -> Optional[str]:
        metodo = getattr(self, f"_sem_{nodo.tipo}", None)
        if metodo:
            return metodo(nodo)
        if nodo.tipo in self.OPS_CMP:
            return self._sem_comparacion(nodo)
        # Nodos de operación aritmética
        if nodo.tipo in ("ADD", "SUB", "MUL", "DIV"):
            return self._sem_aritmetica(nodo)
        # Pasar por nodos contenedores
        for hijo in nodo.hijos:
            self.analizar(hijo)
        return None

    # ── Hojas ────────────────────────────────────────────────

    def _sem_NUM_INT(self, nodo):   return "int"
    def _sem_NUM_FLOAT(self, nodo): return "float"
    def _sem_STR(self, nodo):       return "string"
    def _sem_BOOL(self, nodo):      return "bool"
    def _sem_TIPO(self, nodo):      return nodo.valor

    def _sem_ID(self, nodo) -> str:
        try:
            entrada = self.tabla.obtener(nodo.valor, nodo.linea)
            return entrada.tipo
        except SemanticError as e:
            self.errores.append(e)
            return "desconocido"

    # ── Operaciones aritméticas ──────────────────────────────

    def _sem_aritmetica(self, nodo) -> str:
        tipo_izq = self.analizar(nodo.hijos[0])
        tipo_der = self.analizar(nodo.hijos[1])
        resultado = TIPOS_ARIT.get((tipo_izq, tipo_der))
        if resultado is None:
            self.errores.append(SemanticError(
                f"Operación '{nodo.tipo}' no soportada entre "
                f"'{tipo_izq}' y '{tipo_der}'.",
                nodo.linea
            ))
            return "desconocido"
        return resultado

    # ── Comparaciones ────────────────────────────────────────

    def _sem_comparacion(self, nodo) -> str:
        self.analizar(nodo.hijos[0])
        self.analizar(nodo.hijos[1])
        return "bool"

    # ── Sentencias ───────────────────────────────────────────

    def _sem_PROGRAM(self, nodo):
        for hijo in nodo.hijos:
            self.analizar(hijo)

    def _sem_DECL(self, nodo):
        tipo_decl = nodo.hijos[0].valor
        nombre    = nodo.hijos[1].valor
        tipo_expr = self.analizar(nodo.hijos[2])

        # Verificar compatibilidad de tipos
        if tipo_expr not in (tipo_decl, "desconocido"):
            # Permitir int → float implícitamente
            if not (tipo_decl == "float" and tipo_expr == "int"):
                self.errores.append(SemanticError(
                    f"Tipo incompatible: se declaró '{tipo_decl}' "
                    f"pero la expresión es '{tipo_expr}'.",
                    nodo.linea
                ))

        # Evaluar valor para la tabla (si es posible)
        try:
            valor = self._evaluar(nodo.hijos[2])
        except Exception:
            valor = None

        try:
            self.tabla.declarar(nombre, tipo_decl, valor, nodo.linea)
        except SemanticError as e:
            self.errores.append(e)

    def _sem_ASSIGN(self, nodo):
        nombre    = nodo.hijos[0].valor
        tipo_expr = self.analizar(nodo.hijos[1])
        try:
            entrada = self.tabla.obtener(nombre, nodo.linea)
            if tipo_expr not in (entrada.tipo, "desconocido"):
                if not (entrada.tipo == "float" and tipo_expr == "int"):
                    self.errores.append(SemanticError(
                        f"No se puede asignar '{tipo_expr}' "
                        f"a variable de tipo '{entrada.tipo}'.",
                        nodo.linea
                    ))
            try:
                valor = self._evaluar(nodo.hijos[1])
                self.tabla.asignar(nombre, valor, nodo.linea)
            except Exception:
                pass
        except SemanticError as e:
            self.errores.append(e)

    def _sem_IF(self, nodo):
        tipo_cond = self.analizar(nodo.hijos[0])
        if tipo_cond not in ("bool", "desconocido"):
            self.errores.append(SemanticError(
                f"La condición del 'if' debe ser booleana, "
                f"se obtuvo '{tipo_cond}'.",
                nodo.linea
            ))
        self.tabla.entrar_ambito()
        self.analizar(nodo.hijos[1])
        self.tabla.salir_ambito()
        if len(nodo.hijos) == 3:
            self.tabla.entrar_ambito()
            self.analizar(nodo.hijos[2])
            self.tabla.salir_ambito()

    def _sem_WHILE(self, nodo):
        tipo_cond = self.analizar(nodo.hijos[0])
        if tipo_cond not in ("bool", "desconocido"):
            self.errores.append(SemanticError(
                f"La condición del 'while' debe ser booleana, "
                f"se obtuvo '{tipo_cond}'.",
                nodo.linea
            ))
        self.tabla.entrar_ambito()
        self.analizar(nodo.hijos[1])
        self.tabla.salir_ambito()

    def _sem_BLOCK(self, nodo):
        for hijo in nodo.hijos:
            self.analizar(hijo)

    def _sem_PRINT(self, nodo):
        self.analizar(nodo.hijos[0])

    def _sem_RETURN(self, nodo):
        self.analizar(nodo.hijos[0])

    # ── Evaluador parcial (para poblar tabla de símbolos) ────

    def _evaluar(self, nodo: Nodo):
        """Evalúa constantes y expresiones simples en tiempo de análisis."""
        if nodo.tipo == "NUM_INT":   return nodo.valor
        if nodo.tipo == "NUM_FLOAT": return nodo.valor
        if nodo.tipo == "STR":       return nodo.valor
        if nodo.tipo == "BOOL":      return nodo.valor
        if nodo.tipo == "ID":
            return self.tabla.obtener_valor(nodo.valor, nodo.linea)

        ops = {
            "ADD": lambda a, b: a + b,
            "SUB": lambda a, b: a - b,
            "MUL": lambda a, b: a * b,
            "DIV": lambda a, b: a / b,
        }
        if nodo.tipo in ops:
            return ops[nodo.tipo](
                self._evaluar(nodo.hijos[0]),
                self._evaluar(nodo.hijos[1])
            )
        cmp_ops = {
            "CMP_>":  lambda a, b: a > b,
            "CMP_<":  lambda a, b: a < b,
            "CMP_>=": lambda a, b: a >= b,
            "CMP_<=": lambda a, b: a <= b,
            "CMP_==": lambda a, b: a == b,
            "CMP_!=": lambda a, b: a != b,
        }
        if nodo.tipo in cmp_ops:
            return cmp_ops[nodo.tipo](
                self._evaluar(nodo.hijos[0]),
                self._evaluar(nodo.hijos[1])
            )
        raise ValueError(f"No se puede evaluar nodo: {nodo.tipo}")


# ═════════════════════════════════════════════════════════════
# FASE 4 — GENERACIÓN DE CÓDIGO INTERMEDIO (Tres Direcciones)
# ═════════════════════════════════════════════════════════════

class GeneradorCodigo:
    """
    Fase 4 — Generación de Código de Tres Direcciones (TAC).

    El código de tres direcciones tiene la forma:
        result = operando1  op  operando2

    También genera etiquetas y saltos condicionales para
    estructuras de control (if, while).

    Ejemplo de salida:
        t0 = a * 3
        t1 = t0 + 2
        b = t1
        if b > 20 goto L0
        goto L1
        L0:
          t2 = a + 1
          a = t2
        L1:
    """

    def __init__(self):
        self._instrucciones: List[str] = []
        self._contador_temp  = 0
        self._contador_label = 0

    def _nuevo_temp(self) -> str:
        """Genera un nombre de temporal único: t0, t1, t2, …"""
        nombre = f"t{self._contador_temp}"
        self._contador_temp += 1
        return nombre

    def _nueva_etiqueta(self) -> str:
        """Genera una etiqueta única: L0, L1, L2, …"""
        nombre = f"L{self._contador_label}"
        self._contador_label += 1
        return nombre

    def _emit(self, instruccion: str, indent: int = 0) -> None:
        self._instrucciones.append("  " * indent + instruccion)

    # ── Punto de entrada ────────────────────────────────────

    def generar(self, nodo: Nodo) -> List[str]:
        """Recorre el AST y produce la lista de instrucciones TAC."""
        self._generar_nodo(nodo)
        return self._instrucciones

    def imprimir(self) -> None:
        sep = "─" * 50
        print(f"\n{sep}")
        print(f"  {'CÓDIGO DE TRES DIRECCIONES (TAC)':^46}")
        print(sep)
        for i, instr in enumerate(self._instrucciones):
            print(f"  {i:3}│ {instr}")
        print(sep)

    # ── Generación por tipo de nodo ──────────────────────────

    def _generar_nodo(self, nodo: Nodo) -> Optional[str]:
        """Despacha la generación según el tipo de nodo."""
        metodo = getattr(self, f"_gen_{nodo.tipo}", None)
        if metodo:
            return metodo(nodo)
        # Operadores aritméticos y de comparación
        if nodo.tipo in ("ADD","SUB","MUL","DIV"):
            return self._gen_aritmetica(nodo)
        if nodo.tipo.startswith("CMP_"):
            return self._gen_comparacion(nodo)
        return None

    # ── Hojas ────────────────────────────────────────────────

    def _gen_NUM_INT(self, nodo):   return str(nodo.valor)
    def _gen_NUM_FLOAT(self, nodo): return str(nodo.valor)
    def _gen_STR(self, nodo):       return f'"{nodo.valor}"'
    def _gen_BOOL(self, nodo):      return "true" if nodo.valor else "false"
    def _gen_ID(self, nodo):        return nodo.valor

    # ── Operaciones aritméticas ──────────────────────────────

    def _gen_aritmetica(self, nodo: Nodo) -> str:
        simbolo = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/"}
        izq  = self._generar_nodo(nodo.hijos[0])
        der  = self._generar_nodo(nodo.hijos[1])
        temp = self._nuevo_temp()
        self._emit(f"{temp} = {izq} {simbolo[nodo.tipo]} {der}")
        return temp

    def _gen_comparacion(self, nodo: Nodo) -> str:
        op_map = {
            "CMP_>":  ">",  "CMP_<":  "<",
            "CMP_>=": ">=", "CMP_<=": "<=",
            "CMP_==": "==", "CMP_!=": "!=",
        }
        izq  = self._generar_nodo(nodo.hijos[0])
        der  = self._generar_nodo(nodo.hijos[1])
        temp = self._nuevo_temp()
        self._emit(f"{temp} = {izq} {op_map[nodo.tipo]} {der}")
        return temp

    # ── Sentencias ───────────────────────────────────────────

    def _gen_PROGRAM(self, nodo: Nodo):
        for hijo in nodo.hijos:
            self._generar_nodo(hijo)

    def _gen_DECL(self, nodo: Nodo):
        nombre = nodo.hijos[1].valor
        val    = self._generar_nodo(nodo.hijos[2])
        self._emit(f"{nombre} = {val}    // decl {nodo.hijos[0].valor}")

    def _gen_ASSIGN(self, nodo: Nodo):
        nombre = nodo.hijos[0].valor
        val    = self._generar_nodo(nodo.hijos[1])
        self._emit(f"{nombre} = {val}")

    def _gen_IF(self, nodo: Nodo):
        """
        if (cond) { bloque_then } else { bloque_else }

        TAC:
          <cond_temp> = ...
          if <cond_temp> goto L_then
          goto L_else          (o L_fin si no hay else)
          L_then:
            ...bloque then...
            goto L_fin
          L_else:              (solo si hay else)
            ...bloque else...
          L_fin:
        """
        cond_val  = self._generar_nodo(nodo.hijos[0])
        l_then    = self._nueva_etiqueta()
        l_fin     = self._nueva_etiqueta()
        tiene_else = len(nodo.hijos) == 3

        self._emit(f"if {cond_val} goto {l_then}")

        if tiene_else:
            l_else = self._nueva_etiqueta()
            self._emit(f"goto {l_else}")
        else:
            self._emit(f"goto {l_fin}")

        # Bloque then
        self._emit(f"{l_then}:")
        self._generar_nodo(nodo.hijos[1])
        self._emit(f"goto {l_fin}")

        # Bloque else (opcional)
        if tiene_else:
            self._emit(f"{l_else}:")
            self._generar_nodo(nodo.hijos[2])

        self._emit(f"{l_fin}:")

    def _gen_WHILE(self, nodo: Nodo):
        """
        while (cond) { bloque }

        TAC:
          L_inicio:
            <cond_temp> = ...
            if <cond_temp> goto L_cuerpo
            goto L_fin
          L_cuerpo:
            ...bloque...
            goto L_inicio
          L_fin:
        """
        l_inicio = self._nueva_etiqueta()
        l_cuerpo = self._nueva_etiqueta()
        l_fin    = self._nueva_etiqueta()

        self._emit(f"{l_inicio}:")
        cond_val = self._generar_nodo(nodo.hijos[0])
        self._emit(f"if {cond_val} goto {l_cuerpo}")
        self._emit(f"goto {l_fin}")
        self._emit(f"{l_cuerpo}:")
        self._generar_nodo(nodo.hijos[1])
        self._emit(f"goto {l_inicio}")
        self._emit(f"{l_fin}:")

    def _gen_BLOCK(self, nodo: Nodo):
        for hijo in nodo.hijos:
            self._generar_nodo(hijo)

    def _gen_PRINT(self, nodo: Nodo):
        val = self._generar_nodo(nodo.hijos[0])
        self._emit(f"print {val}")

    def _gen_RETURN(self, nodo: Nodo):
        val = self._generar_nodo(nodo.hijos[0])
        self._emit(f"return {val}")

    def _gen_TIPO(self, nodo: Nodo):
        return nodo.valor


# ═════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — compilar()
# ═════════════════════════════════════════════════════════════

def compilar(codigo: str, nombre: str = "programa",
             verbose: bool = True) -> bool:
    """
    Ejecuta las cuatro fases del compilador sobre el código fuente.

    Retorna True si la compilación fue exitosa, False si hubo errores.
    """
    SEP  = "═" * 62
    sep2 = "─" * 62

    if verbose:
        print(f"\n{SEP}")
        print(f"  Compilando: {nombre}")
        print(SEP)
        print("CÓDIGO FUENTE:")
        for i, linea in enumerate(codigo.strip().splitlines(), 1):
            print(f"  {i:3}│ {linea}")

    errores_totales: List[CompilerError] = []

    # ── FASE 1: Análisis Léxico ──────────────────────────────
    tokens, errores_lex = analizar_lexico(codigo)
    errores_totales.extend(errores_lex)

    if verbose:
        print(f"\n{'─'*62}")
        print("  FASE 1 — TOKENS")
        print(sep2)
        for t in tokens:
            if t.tipo != "EOF":
                print(f"  {t}")
        if errores_lex:
            print(f"\n  ⚠ {len(errores_lex)} error(es) léxico(s):")
            for e in errores_lex:
                print(f"    {e}")

    # Si hay errores léxicos no se puede continuar con sintaxis
    if errores_lex:
        print(f"\n❌ Compilación abortada por errores léxicos.\n")
        return False

    # ── FASE 2: Análisis Sintáctico ──────────────────────────
    try:
        parser = Parser(tokens)
        ast    = parser.parsear()
    except SyntaxErr as e:
        errores_totales.append(e)
        print(f"\n{e}")
        print("❌ Compilación abortada por error sintáctico.\n")
        return False

    if verbose:
        print(f"\n{'─'*62}")
        print("  FASE 2 — AST")
        print(sep2)
        imprimir_ast(ast)

    # ── FASE 3: Análisis Semántico ───────────────────────────
    semantico = AnalizadorSemantico()
    semantico.analizar(ast)
    errores_totales.extend(semantico.errores)

    if verbose:
        semantico.tabla.imprimir()
        if semantico.errores:
            print(f"\n  ⚠ {len(semantico.errores)} error(es) semántico(s):")
            for e in semantico.errores:
                print(f"    {e}")

    # ── FASE 4: Generación de Código ─────────────────────────
    if not semantico.errores:
        generador = GeneradorCodigo()
        generador.generar(ast)
        if verbose:
            generador.imprimir()

    # ── Resultado ────────────────────────────────────────────
    if errores_totales:
        print(f"\n❌ Compilación fallida — "
              f"{len(errores_totales)} error(es) encontrado(s).\n")
        return False
    else:
        if verbose:
            print(f"\n✅ Compilación exitosa.\n")
        return True


# ═════════════════════════════════════════════════════════════
# CASOS DE PRUEBA
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── Prueba 1: expresiones aritméticas con precedencia ────
    compilar("""
int a = 10;
int b = a * 3 + 2;
print(b);
""", nombre="Prueba 1 — Expresiones aritméticas")

    # ── Prueba 2: condicional if / else ──────────────────────
    compilar("""
int x = 10;
int y = x * 3 + 2;

if (y > 20) {
    x = x + 1;
    print(x);
} else {
    print(y);
}
""", nombre="Prueba 2 — Condicional if / else")

    # ── Prueba 3: bucle while ────────────────────────────────
    compilar("""
int i = 0;
int suma = 0;

while (i < 5) {
    suma = suma + i;
    i = i + 1;
}

print(suma);
""", nombre="Prueba 3 — Bucle while")

    # ── Prueba 4: error semántico — variable no declarada ────
    compilar("""
int x = 5;
y = x + 1;
""", nombre="Prueba 4 — Error: variable no declarada")

    # ── Prueba 5: error semántico — tipo incompatible ────────
    compilar("""
int z = "hola";
""", nombre="Prueba 5 — Error: tipo incompatible")

    # ── Prueba 6: error léxico — carácter inválido ───────────
    compilar("""
int a = 5;
int b = a @ 2;
""", nombre="Prueba 6 — Error: carácter inválido")
