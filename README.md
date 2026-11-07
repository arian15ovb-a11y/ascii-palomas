# palomas

Dos palomas — **corzo** y **miranda** — cruzando un cielo de atardecer, dibujadas
carácter a carácter en ASCII.

Un único archivo de Python, sin dependencias de arte: el cielo es un campo de
ruido fBM, la ciudad es una silueta procedural con ventanas que parpadean, y cada
paloma se dibuja con trazos (cuerpo + arco del ala) cuyo batir es una curva real,
no un sprite que salta entre poses.

    python palomas.py                # la animación en la terminal (Ctrl-C para parar)
    python palomas.py --render       # genera palomas.gif y palomas.mp4
    python palomas.py --dump 3.6     # imprime la rejilla de caracteres en t=3.6s

## Las dos palomas

| | corzo | miranda |
|---|---|---|
| Color | bronce / ámbar | marfil / azul frío |
| Tamaño | mayor | menor |
| Vuelo | sube primero, se lanza en el cruce | teje por debajo, corta en diagonal |

Cada una lleva su nombre pegado al cuerpo con una aguja de un carácter, así que se
sabe en todo momento cuál es cuál.

## Cómo está hecho

- **Rejilla**: 132 × 56 caracteres, 20 fps, 9 segundos.
- **Cielo**: gradiente índigo → malva → ámbar de horizonte, con ruido fBM lento
  encima. La densidad del ruido se mapea a una rampa de caracteres; la mayor parte
  del cuadro queda vacía a propósito.
- **Estrellas**: 140 puntos con fase propia; titilan y se apagan al acercarse al
  horizonte.
- **Ciudad**: bloques generados con semilla fija, ventanas encendidas con parpadeo
  lento, línea de agua con reflejos.
- **Plumas**: partículas que caen con vaivén y sólo se ven cerca de las palomas.
- **Palomas**: el cuerpo es el glifo `\_` `(` `o` `>`; el ala es un arco de Bézier
  cuadrático cuyos extremos suben y bajan con el batir. Un detalle que costó
  encontrar: en una rejilla de caracteres una fila mide ~1,75 veces lo que una
  columna, así que hay que comprimir las alturas (`ASPECT`) o todo sale aplastado.
- **Rótulo**: `palomas` se escribe carácter a carácter al final, con
  `corzo & miranda` debajo.

## Requisitos

    pip install pillow numpy

y `ffmpeg` en el PATH para `--render` (usa `consola.ttf` para rasterizar, presente
en Windows; en Linux/macOS cambia `FONT_PATH` por cualquier monoespaciada).

## Salida

- `palomas.gif` — 1100 px de ancho, para previsualizar en el README.
- `palomas.mp4` — H.264, 20 fps, para verlo entero con el detalle fino.

## Licencia

Sin licencia declarada todavía: el código es de quien lo escribió.
