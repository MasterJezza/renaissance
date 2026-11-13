# Bakgrundsbilder – klassisk skulptur & chiaroscuro

Ett urval skrivbordsbakgrunder i samma anda som antik marmorskulptur och
barockens dramatiska ljus/mörker (tenebrism). Alla verk kommer från
The Metropolitan Museum of Art och är **Public Domain (CC0)** via Mets Open Access.

## Mappar

- `bilder/` – verken i originalproportioner (längsta sidan max 3840 px).
- `16x9/` – färdiga 3840×2160-bakgrunder: motivet förskjutet åt höger,
  mörk suddig utfyllnad och mjuk vinjett.

## Verk

| # | Verk | Konstnär | Källa |
|---|------|----------|-------|
| 01 | Ugolino och hans söner (1865–67) | Jean-Baptiste Carpeaux | [Met 204812](https://www.metmuseum.org/art/collection/search/204812) |
| 02 | Perseus med Medusas huvud (1804–06) | Antonio Canova | [Met 204758](https://www.metmuseum.org/art/collection/search/204758) |
| 03 | Medusas huvud (1806–07) | Antonio Canova | [Met 204759](https://www.metmuseum.org/art/collection/search/204759) |
| 04 | Sårad amazon, marmor | Romersk kopia efter grekiskt original | [Met 253373](https://www.metmuseum.org/art/collection/search/253373) |
| 05 | Sårad krigare, marmor | Romersk kopia efter grekiskt original | [Met 251929](https://www.metmuseum.org/art/collection/search/251929) |
| 06 | Porträtt av kejsar Caracalla (212–217) | Romersk | [Met 253592](https://www.metmuseum.org/art/collection/search/253592) |
| 07 | Petrus tårar (ca 1612–13) | Jusepe de Ribera | [Met 441971](https://www.metmuseum.org/art/collection/search/441971) |
| 08 | Petrus förnekelse (1610) | Caravaggio | [Met 437986](https://www.metmuseum.org/art/collection/search/437986) |
| 09 | Den ångerfulla Magdalena | Georges de La Tour | [Met 436839](https://www.metmuseum.org/art/collection/search/436839) |
| 10 | Aristoteles med en byst av Homeros (1653) | Rembrandt | [Met 437394](https://www.metmuseum.org/art/collection/search/437394) |
| 11 | Gammal kvinna som ber | Matthias Stom | [Met 437757](https://www.metmuseum.org/art/collection/search/437757) |
| 12 | Sokrates död (1787) | Jacques-Louis David | [Met 436105](https://www.metmuseum.org/art/collection/search/436105) |

## Göra fler 16:9-versioner

Kräver ImageMagick. Kör från `bilder/`:

```bash
W=3840; H=2160
for f in *.jpg; do
  w=$(identify -format %w "$f"); h=$(identify -format %h "$f"); fw=$(( w * H / h ))
  if [ $fw -lt 3000 ]; then x=$(( W*58/100 - fw/2 )); else x=$(( (W-fw)/2 )); fi
  e=$(( fw * 14 / 100 )); m=$(( fw - 2*e ))
  convert \( "$f" -resize ${W}x${H}^ -gravity center -extent ${W}x${H} -resize 8% -blur 0x10 -resize ${W}x${H}! -modulate 50,75 \
             \( -size ${W}x${H} radial-gradient:none-black -channel A -evaluate multiply 0.6 +channel \) -composite \) \
          \( "$f" -resize ${fw}x${H}! \
             \( \( -size ${H}x${e} gradient:white-black -rotate 90 \) \( -size ${m}x${H} xc:white \) \( -size ${H}x${e} gradient:white-black -rotate -90 \) +append \) \
             -alpha off -compose CopyOpacity -composite \) \
          -compose over -gravity northwest -geometry +${x}+0 -composite \
          \( -size ${W}x${H} radial-gradient:none-black -channel A -evaluate multiply 0.25 +channel \) -composite \
          -quality 90 "../16x9/${f%.jpg}-16x9.jpg"
done
```
