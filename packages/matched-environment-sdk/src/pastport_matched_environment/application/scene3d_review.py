"""Shared VR/3D review markup and original per-result source bridge."""
from pathlib import Path


def shared_review_markup(text: str) -> str:
    for before, after in (
        ("VR中显示的内容", "全景 / 3D 共用介绍"),
        ("修改VR弹窗文字", "修改全景与3D介绍"),
        ("保存VR显示内容", "保存介绍（同步全景与3D）"),
        ("打开VR查看", "在全景中查看"),
        ("回到VR关闭弹窗，再点击编号即可看到更新", "全景与3D将使用同一份新介绍"),
        ("/api/vr-content", "/api/scene3d/content"),
    ):
        text = text.replace(before, after)
    if 'id="scene3d-review-link"' not in text:
        text = text.replace(
            "$('detail').innerHTML=`",
            "$('detail').innerHTML=`"
            "<section><h3>3D 位置与展示</h3><p>"
            '<a id="scene3d-review-link" href="/scene3d/index.html?object_id=${id}">'
            "在 3D 中定位、拖拽此编号</a> · "
            '<a href="/vr_trial/index.html?object_id=${id}">在原全景中对照</a></p>'
            '<p class="sub">介绍共用；三维位置可独立拖拽保存，原全景位置保留。</p></section>',
            1,
        )
        text = text.replace(
            "await load();$('vr-result')",
            "window.dispatchEvent(new CustomEvent('pastport-content-saved',"
            "{detail:{object_id:id}}));await load();$('vr-result')",
            1,
        )
        text += '\n<script src="/scene3d/shared_content.js"></script>\n'
    return text


def connect_review(root: Path) -> None:
    review = root / "index.html"
    review.write_text(shared_review_markup(review.read_text()))
    source = root / "vr_trial/index.html"
    html = source.read_text()
    if "pastport-source-ready" not in html:
        marker = "new window.PastPortPositionEditor(r).initialize();"
        if marker not in html:
            raise ValueError("Source viewer bridge counterpart changed")
        html = html.replace(
            marker,
            marker + "window.PastPortSourceHost=r;"
            "window.dispatchEvent(new Event('pastport-source-ready'));",
            1,
        )
        html += '\n<script src="/scene3d/shared_content.js"></script>\n'
        source.write_text(html)
