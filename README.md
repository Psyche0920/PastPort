<div align="center">

![PastPort — illustrated heritage storytelling banner](.github/showcase/hero.webp)

# PastPort

**Interactive heritage stories, explored through your choices.**

English · [中文](README_ZH.md)

[Watch the demo](#demo) &nbsp; / &nbsp; [See the experience](#experience) &nbsp; / &nbsp; [Run locally](#run-locally)

</div>

<a id="demo"></a>

## Take a look

<table>
<tr>
<td width="50%" align="center">
<a href="https://drive.google.com/file/d/1m5JBXLTCtL9ITxiZJSNey-Ev8xvFqccy/view?usp=sharing"><img src=".github/showcase/demo.svg" alt="Watch the demo" width="100%"></a>
<br><a href="https://drive.google.com/file/d/1m5JBXLTCtL9ITxiZJSNey-Ev8xvFqccy/view?usp=sharing"><strong>Watch the demo</strong></a>
</td>
<td width="50%" align="center">
<a href="https://docs.google.com/presentation/d/1AGZIhHhWdMs3ogOZTk8CjLOHduYBt1xg/edit?slide=id.p1#slide=id.p1"><img src=".github/showcase/presentation-cover.png" alt="See the presentation" width="100%"></a>
<br><a href="https://docs.google.com/presentation/d/1AGZIhHhWdMs3ogOZTk8CjLOHduYBt1xg/edit?slide=id.p1#slide=id.p1"><strong>See the presentation</strong></a>
</td>
</tr>
</table>

Demo: no login needed. Presentation: viewing permission required.

<a id="experience"></a>

## Pick a place. Follow its clues. Make a choice.

PastPort turns historical sources into interactive 3D stories. Explore a place, meet fictional characters and investigate the evidence behind the story.

### Discover a place

![Browse heritage locations on the player map.](.github/showcase/map.webp)

### Step inside

![Explore the scanned space and follow the story.](.github/showcase/explore.webp)

<table>
<tr>
<td width="50%" valign="top">
<a href=".github/showcase/characters.webp"><img src=".github/showcase/characters.webp" alt="Get to know the characters and what matters to them." width="100%"></a>
<h3>Meet the people</h3>
Get to know the characters and what matters to them.
</td>
<td width="50%" valign="top">
<a href=".github/showcase/investigate.webp"><img src=".github/showcase/investigate.webp" alt="Compare a source photograph with its altered game copy." width="100%"></a>
<h3>Look closer</h3>
Compare a source photograph with its altered game copy.
</td>
</tr>
</table>

**Real sources. Fictional stories. A clear distinction.** Historical context comes with references; the characters and plot are fiction. In the Eyne Bey demo, a separate Şeker Han scan provides the 3D stage. The banner is a brand illustration, not a historical reconstruction.

<a id="run-locally"></a>

## Run locally

[Download the featured game](https://github.com/Psyche0920/PastPort/releases/download/eyne-bey-seker-han-demo-2026-11-08-r2/eyne-bey-seker-han.tar.gz) · [Browse all releases](https://github.com/Psyche0920/PastPort/releases)

<details>
<summary>Setup and launch instructions</summary>

You’ll need Git, uv, Python 3.12, Node.js 22.13+ and a browser with WebGL.

### First setup

```sh
git clone https://github.com/Psyche0920/PastPort.git
cd PastPort
uv sync --extra authoring --extra game-making
uv run python -m pastport organizer-init
```

Create your local administrator account when prompted. Existing accounts and project data are retained.

### Start the creator workspace

```sh
uv run python -m pastport organizer
```

Open [Organizer](http://127.0.0.1:18840/organizer/) and sign in.

### Start the player platform in a second terminal

```sh
node frontend/player/server.mjs
```

Open the [player map](http://127.0.0.1:18851/). Import a game in Organizer and publish it to a place before launching it from the map. Keep both terminals open; Ctrl+C stops each service.

Each installation stores its own files, accounts and saves. Updating the repository does not copy them between computers.

</details>

<details>
<summary>Project notes</summary>

PastPort is a hackathon prototype. Content needs human review before publication.

[Maintainer documentation](docs/TECHNICAL_PRD_EN.md) · [Historical archive](https://github.com/Psyche0920/PastPort/tree/archive/hackathon-docs-2026-11-11) · [MIT license](LICENSE)

</details>

---

Built by **Mert Aslan, Weijia Han and Weng Man Cheung** for the ROOT&CODE Hackathon, with support from **42 Heilbronn**.
