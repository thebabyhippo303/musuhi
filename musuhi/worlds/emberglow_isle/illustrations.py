"""Hand-drawn sprite stamps for the keepers' field guide."""
from PIL import Image, ImageDraw
from functools import lru_cache


@lru_cache(None)
def portrait(side, pose=0):
    im = Image.new("RGBA", (42, 40))
    d = ImageDraw.Draw(im)
    line, poly, box, oval = d.line, d.polygon, d.rectangle, d.ellipse
    ink = "#25233e"
    if side == "p2":
        # Velvet moth, folded wings and rain cape.
        poly([(13,18),(5,12+pose),(2,17+pose),(4,28),(15,32)], "#533758", ink)
        poly([(24,19),(32,12+pose),(35,17+pose),(32,29),(23,33)], "#644162", ink)
        line([(5,18+pose),(9,24),(12,25)], "#be8986", 2)
        line([(31,18+pose),(27,24),(25,25)], "#be8986", 2)
        box((12,32,16,36), ink); box((21,32,25,36), ink)
        poly([(15,17),(22,17),(29,32),(22,34),(18,31),(11,34),(8,31)], "#df963f", ink)
        poly([(15,18),(19,19),(16,29),(10,31)], "#ffda71")
        oval((10,6,25,22), ink); oval((11,7,24,20), "#603d58")
        poly([(11,12),(16,14),(20,12),(24,12),(23,18),(19,20),(14,19)], "#ad797f")
        box((14,14,15,16), "#ffecac"); box((21,14,22,16), "#ffecac")
        line([(14,8),(12,4),(9,2),(7,3)], "#d7a89b", 2)
        line([(21,8),(23,4),(27,2),(29,3)], "#d7a89b", 2)
        line([(23,22),(28,24),(32,21)], ink, 3)
        d.arc((30,17,37,26), 180,360, "#ffe6a2")
        box((30,22,38,32), ink); box((31,23,37,31), "#d59a49")
        box((32,24,36,29), "#ffef9b"); box((33,25,35,28), "#fffadd")
        line((29,22,39,22), "#ffda79", 2)
    else:
        # Basalt gardener, verdigris seams and a growing crown.
        box((10,32,15,37), ink); box((23,32,28,37), ink)
        poly([(12,19),(26,19),(30,27),(27,34),(10,34),(8,26)], "#548b77", ink)
        poly([(12,20),(18,21),(17,28),(10,31)], "#8eb791")
        poly([(19,24),(26,23),(25,31),(18,32)], "#426c68")
        poly([(8,20),(4,23),(5,29),(10,31),(12,25)], "#799f84", ink)
        poly([(29,20),(34,21),(36,27),(30,30),(27,26)], "#648a79", ink)
        poly([(10,9),(17,5),(26,7),(30,12),(28,20),(21,24),(11,21),(8,15)], "#689782", ink)
        poly([(12,10),(18,7),(25,9),(26,11),(15,13),(10,12)], "#a7caa0")
        poly([(12,14),(26,12),(25,18),(14,20)], "#364e54")
        box((15,15,17,17), "#f6edab"); box((22,14,24,16), "#f6edab")
        line([(18,8),(18,4),(21,2)], "#dbd590", 2)
        poly([(18,6),(13,5),(10,1),(15,1),(19,4)], "#b3de84")
        poly([(19,4),(23,0),(28,0),(25,4),(20,6)], "#70c791")
        line([(10,20),(27,30)], "#d9b880", 2)
        box((19,26,28,32), "#705154", ink); box((20,26,27,28), "#d4a16c")
    return im


def sprite(im, x, y, side, pose=0, scale=1):
    stamp = portrait(side, pose)
    if scale != 1:
        stamp = stamp.resize((42*scale,40*scale), Image.Resampling.NEAREST)
    im.paste(stamp, (int(x)-21*scale, int(y)-38*scale), stamp)
