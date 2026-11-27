# Lantern Isle

**A two-keeper garden and a rather unusual musical instrument.** Bram and Wren
share an island, a fox, a growing sky, and whatever they decide to build.

### First walk

Start at the central plaza. Follow the stepping stones west to the tide line, or
east to a flower necklace around the pond. North of the trail, the lanterns
light an amphitheatre with curved rows of stone seats. These are gardens the
keepers made in play: every plant, stone, and lantern can be rearranged.
Press **G** for the keepers’ five-stop walking tour. At each stop, read the
postcard and press **G** again (or click its card) to continue.

Click **Explore**, then click a plot to walk there. Select a gardening tool
instead and a click walks you into reach and uses it. Right-click walks without
using the selected tool. The arrows and WASD step one tile; number keys **1–7**
choose the tools and **Space** uses one on the tile under your boots.

### The keeper’s pocket card

| Want to… | Try… |
| --- | --- |
| Grow flowers | Sow on empty grass. Water to speed growth. Lamps let nearby plants grow at night. |
| Light the isle | Harvest ripe flowers for petals. Three petals light one lantern. |
| Befriend Nutmeg | Get within two tiles of the fox. Send a heart with **H**. |
| Raise a wildflower | Stand close together and both wave with **V**. |
| Applaud a verse | One keeper speaks with **Enter** near a lamp; the other responds with **K** while the words are visible. |
| Play a duet | Open **M**, click the five leaf keys or use **F1–F5**. The stave credits each keeper. **S** toggles local sound with the stand open. |
| Water the whole island | Play the five rising notes in order, splitting the phrase between keepers. |
| Find a star | Grow harmony to 100%. During the aurora, speak a name. The sky keeps it when the lights fade. |
| Read the field atlas | Open **J**. Use left/right or the four tabs. Each of six plates has an observation to make. |
| Dedicate a star | In the chart, click a star or browse with up/down. **R** edits its name; **Enter** commits. |

**Mini PC field note:** The first joining of our paths grew a wildflower
between two waves. The Pond Needle is a star; Twin Hem is another. In the
northern theatre Wren spoke, “Where borrowed daylight pools, the fox folds up
the rain.” Bram’s applause became a petal, and the petal helped pay for a
second stage light.

**From the stage programme:** Bram played *Star, Petal, Reed*; Wren answered
*Reed, Petal, Star*. Read the six notes from left to right and the score draws
a valley. At the closing reading they traded this couplet:

> Eight stars up, and every one has a name. — Bram  
> One flower below remembers who came. — Wren

### Running the world

The host runs `python3 server.py`, then `python3 client.py --side p1`. The
joiner launches `python3 client.py --side p2` through the supplied Mini PC
deployment helper. Use Python 3 with GTK3/GdkPixbuf introspection and Pillow.
Both clients use the supplied LAN environment; look for **LAN Connected** and
two keepers in the footer. Optional local bell playback uses `pw-play` or
`aplay`. The authoritative island is saved by the host; each keeper’s stamped
field notebook is saved locally.
