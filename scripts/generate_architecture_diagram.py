#!/usr/bin/env python3
"""Generate architecture-overview-serializer.png for README and blog."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUTPUT = Path(__file__).resolve().parents[1] / "images" / "architecture-overview-serializer.png"

CANVAS_W = 18.0
PANEL_X = 0.35
PANEL_W = CANVAS_W - 0.7
PANEL_INSET = 0.42  # inner padding inside each panel border
FILL_WIDTH = PANEL_W - 2 * PANEL_INSET

# Colors
BG = "#FFFFFF"
PANEL_BG = "#F8FAFC"
BORDER = "#CBD5E1"
TEXT = "#0F172A"
SUBTEXT = "#475569"
VONAGE = "#E53935"
AWS = "#FF9900"
APPRUNNER = "#7C3AED"
AGENTCORE = "#EA580C"
FASTAPI = "#009688"
NGROK = "#1F2937"
WS = "#64748B"
SERIALIZER = "#0EA5E9"
PIPECAT = "#6366F1"

# (title, subtitle, facecolor, edgecolor, relative_weight)
FlowItem = tuple[str, str, str, str, float]


def box(
    ax,
    x,
    y,
    w,
    h,
    title,
    subtitle="",
    fc="#FFFFFF",
    ec=BORDER,
    lw=1.5,
    title_size=7.4,
    sub_size=6.2,
):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        transform=ax.transData,
        zorder=2,
    )
    ax.add_patch(patch)
    title_y = y + h * 0.66 if subtitle else y + h / 2
    ax.text(
        x + w / 2,
        title_y,
        title,
        ha="center",
        va="center",
        fontsize=title_size,
        color=TEXT,
        fontweight="bold",
        zorder=3,
        linespacing=1.05,
    )
    if subtitle:
        ax.text(
            x + w / 2,
            y + h * 0.24,
            subtitle,
            ha="center",
            va="center",
            fontsize=sub_size,
            color=SUBTEXT,
            zorder=3,
            linespacing=1.05,
        )
    return patch


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.35,
            color="#94A3B8",
            shrinkA=0,
            shrinkB=0,
            zorder=1,
        )
    )


def flow_row(ax, y, items: list[FlowItem], box_h: float = 1.02, gap: float = 0.32):
    """Lay out nodes edge-to-edge within the panel, scaling box widths to fill FILL_WIDTH."""
    n = len(items)
    total_gap = gap * (n - 1)
    box_budget = FILL_WIDTH - total_gap
    weight_sum = sum(item[4] for item in items)
    widths = [item[4] / weight_sum * box_budget for item in items]

    x = PANEL_X + PANEL_INSET
    rects: list[tuple[float, float]] = []
    for (title, subtitle, fc, ec, _weight), w in zip(items, widths, strict=True):
        box(ax, x, y, w, box_h, title, subtitle, fc=fc, ec=ec)
        rects.append((x, w))
        x += w + gap

    for i in range(len(rects) - 1):
        x1, w1 = rects[i]
        x2, _w2 = rects[i + 1]
        arrow(ax, x1 + w1 + 0.02, y + box_h / 2, x2 - 0.02, y + box_h / 2)


def main() -> None:
    fig, ax = plt.subplots(figsize=(18, 8), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_xlim(0, CANVAS_W)
    ax.set_ylim(0, 8)
    ax.axis("off")

    ax.text(0.6, 7.45, "Architecture Overview", fontsize=18, fontweight="bold", color=TEXT, ha="left")
    ax.text(
        0.6,
        7.05,
        "Vonage Voice API  →  App Runner /answer  →  AgentCore Runtime  →  Vonage Audio Serializer for Pipecat  →  Pipecat  →  Nova Sonic",
        fontsize=9,
        color=SUBTEXT,
        ha="left",
    )

    serializer: FlowItem = (
        "Vonage Audio\nSerializer\nfor Pipecat",
        "(VonageFrameSerializer)",
        "#E0F2FE",
        SERIALIZER,
        1.45,  # relative weight — wider than default nodes
    )

    # LOCAL DEV panel
    ax.add_patch(
        FancyBboxPatch(
            (PANEL_X, 3.75),
            PANEL_W,
            3.05,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            facecolor=PANEL_BG,
            edgecolor=BORDER,
            linewidth=1.2,
        )
    )
    ax.text(PANEL_X + 0.35, 6.55, "LOCAL DEV", fontsize=11, fontweight="bold", color=TEXT)

    local_items: list[FlowItem] = [
        ("Caller", "", "#FFFFFF", BORDER, 0.75),
        ("Vonage\nVoice API", "Call Control +\nAudio WS", "#FFF5F5", VONAGE, 1.15),
        ("ngrok", "TLS tunnel", "#F3F4F6", NGROK, 0.85),
        ("FastAPI\n/answer", "app/", "#E0F2F1", FASTAPI, 1.0),
        ("WebSocket\n/ws", "app/agent.py", "#F1F5F9", WS, 1.0),
        serializer,
        ("Pipecat\nPipeline", "", "#EEF2FF", PIPECAT, 1.0),
        ("AWS\nNova Sonic", "speech-to-\nspeech", "#FFF7ED", AWS, 1.0),
    ]
    flow_row(ax, 4.55, local_items, box_h=1.02, gap=0.34)

    # PRODUCTION panel
    ax.add_patch(
        FancyBboxPatch(
            (PANEL_X, 0.45),
            PANEL_W,
            3.05,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            facecolor=PANEL_BG,
            edgecolor=BORDER,
            linewidth=1.2,
        )
    )
    ax.text(PANEL_X + 0.35, 3.25, "PRODUCTION", fontsize=11, fontweight="bold", color=TEXT)

    prod_items: list[FlowItem] = [
        ("Caller", "", "#FFFFFF", BORDER, 0.72),
        ("Vonage\nVoice API", "Call Control +\nAudio WS", "#FFF5F5", VONAGE, 1.05),
        ("App Runner\n/answer", "answer/", "#F5F3FF", APPRUNNER, 1.0),
        ("Presigned\nWSS URL", "SigV4 per call", "#F8FAFC", WS, 0.95),
        ("AgentCore\nRuntime", "runtime/\nport 8080", "#FFF7ED", AGENTCORE, 1.0),
        ("BedrockAgent\nCoreApp /ws", "await\naccept()", "#F8FAFC", WS, 1.05),
        serializer,
        ("Pipecat\nPipeline", "", "#EEF2FF", PIPECAT, 0.92),
        ("AWS\nNova Sonic", "speech-to-\nspeech", "#FFF7ED", AWS, 0.92),
    ]
    flow_row(ax, 1.25, prod_items, box_h=1.02, gap=0.30)

    ax.text(
        CANVAS_W / 2,
        0.18,
        "No WebRTC · No EC2/ECS/EKS · Vonage connects to AgentCore via pre-signed WebSocket URL generated at /answer time",
        ha="center",
        va="center",
        fontsize=8.5,
        color=SUBTEXT,
        style="italic",
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, bbox_inches="tight", facecolor=BG, pad_inches=0.25)
    plt.close(fig)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
