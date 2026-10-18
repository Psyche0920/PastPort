# Muradiye immersive scene

Run `python3 -m http.server 8876 --bind 127.0.0.1` at the repository root, then open `http://127.0.0.1:8876/prototype/immersive.html`.

The new entry uses the existing Muradiye chapter, five local publication photographs and Chinese observation records. The original story and saves remain separate. Modern tomb interiors are exploration material, not locations inserted into the 1430s narrative.

## Panorama source

The Bursa Metropolitan Municipality links its public tour from https://www.bursa.bel.tr/sayfa/sanal-turlar-1429 to https://www.bursa.bel.tr/panorama/sanaltarihimekan/index.html. Selecting II. Murat opens https://www.bursa.bel.tr/panorama/sanaltarihimekan/muradiye/index.html.

Public `panorama.xml` identifies the photographer as Bursa Panorama, records contemporary capture dates in September and October 2020, and reserves copyright. This prototype embeds the complete original player, including its branding, controls, links and imagery. No remote panorama tiles, scripts, audio or screenshots are copied into the distribution. Embedding is not a redistribution licence; confirm the owner's permission and deployment terms before publishing this integration.

The second verified tour is the Muradiye madrasa / manuscript museum at https://www.bursa.bel.tr/panorama/sanalmuze/kuran-panorama/index.html, selected through the municipality's virtual-museum directory. Two entry buttons open these distinct official tours. Both begin at an entrance; users follow native white arrows to reach interiors. The complex tour ignores direct-node URL fragments, so unsupported interior shortcuts are deliberately omitted. Native navigation remains under the external player's control: the PastPort card identifies the selected tour, not a synchronized live position. No cross-origin scripting, proxying or credential transfer is used.

## Boundaries and operation

- The remote iframe requires internet and may become unavailable or refuse embedding. A visible original-site link is always provided; the local photo mode remains available.
- Frame load is not treated as proof that panorama tiles loaded. Browser visual inspection is necessary.
- Switching to local photographs unmounts the iframe, stopping its media and rendering. Returning to the tour reloads the selected entry.
- Photo mode preserves hotspot alignment by transforming the complete photograph and hotspot plane together. Pointer drag, bounded zoom, keyboard controls and reset are supported.
- Focus mode hides PastPort overlays without obscuring the remote player's attribution. Fullscreen is optional and reports denial.
- Viewing or inspecting photographs does not unlock game evidence or mutate story saves.
- Local photographs retain their existing source/rights status. This presentation does not grant new publication approval.

No image generation, external AI calls, API keys, package installation or backend changes are needed.
