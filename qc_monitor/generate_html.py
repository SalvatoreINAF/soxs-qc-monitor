import html
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("_", "-")
        .replace("(", "")
        .replace(")", "")
    )


def _infer_section_name(figure: dict) -> str:
    if "section" in figure:
        return figure["section"]

    name = figure.get("name", "").lower()
    title = figure.get("title", "")

    if (
        name.startswith("vis_bias")
        or name.startswith("vis_master_ron")
        or "VIS Bias" in title
        or "VIS Master RON" in title
    ):
        return "Bias"

    if (
        name.startswith("vis_flat")
        or name.startswith("nir_flat")
        or "VIS Flat" in title
        or "NIR Flat" in title
    ):
        return "Flat"

    if name.startswith("nir_dark") or "NIR Dark" in title:
        return "Dark"
    
    if (
        name.startswith("vis_dispersion")
        or name.startswith("nir_dispersion")
        or name.startswith("vis_order_location")
        or name.startswith("nir_order_location")
        or "VIS Dispersion" in title
        or "NIR Dispersion" in title
        or "Order Location" in title
        or "Order Localization" in title
    ):
        return "Dispersion Solution"

    return "Other QC Plots"


def _infer_arm(figure: dict) -> str:
    name = figure.get("name", "").lower()
    title = figure.get("title", "")

    if name.startswith("vis_") or title.startswith("VIS"):
        return "VIS"

    if name.startswith("nir_") or title.startswith("NIR"):
        return "NIR"

    return "OTHER"


def _render_sections(figures: list[dict], plots_relative_dir: str) -> str:
    grouped_by_arm: dict[str, dict[str, list[dict]]] = {
        "VIS": defaultdict(list),
        "NIR": defaultdict(list),
        "OTHER": defaultdict(list),
    }

    for fig in figures:
        arm = _infer_arm(fig)
        section = _infer_section_name(fig)
        grouped_by_arm[arm][section].append(fig)

    def render_arm_tab(arm: str, active: bool = False) -> str:
        tab_id = f"{arm.lower()}-tab"
        active_class = " active" if active else ""

        chunks = [
            f'<div id="{tab_id}" class="tab-content{active_class}">'
        ]

        for section_name, section_figures in grouped_by_arm[arm].items():
            section_id = _slugify(f"{arm}-{section_name}")

            chunks.extend([
                f'  <section id="{section_id}">',
                f"    <h2>{html.escape(section_name)}</h2>",
                '    <div class="plot-grid">',
                "",
            ])

            for fig in section_figures:
                title = fig.get("title", fig.get("name", "Untitled plot"))
                filename = fig["filename"]
                img_path = f"{plots_relative_dir}/{filename}"

                wide = fig.get("wide", False)
                card_class = "plot-card wide" if wide else "plot-card"

                safe_title = html.escape(title)
                safe_img_path = html.escape(img_path, quote=True)

                chunks.extend([
                    f'    <div class="{card_class}">',
                    f"      <h3>{safe_title}</h3>",
                    f'      <a href="{safe_img_path}">',
                    f'        <img src="{safe_img_path}" alt="{safe_title}">',
                    "      </a>",
                    "    </div>",
                    "",
                ])

            chunks.append("    </div>")
            chunks.append("  </section>")

        chunks.append("</div>")
        return "\n".join(chunks)

    return "\n\n".join([
        render_arm_tab("VIS", active=True),
        render_arm_tab("NIR", active=False),
    ])


def generate_html_report(
    plots_cfg: dict,
    output_html: Path,
    template_path: Path | None = None,
):
    figures = plots_cfg.get("figures", [])

    if not figures:
        log.info("No figures configured, skipping HTML report generation")
        return

    if template_path is None:
        template_path = Path(__file__).with_name("template.html")

    output_dir = Path(plots_cfg.get("output_dir", "plots"))
    page_title = plots_cfg.get("page_title", "SOXS Quality Control Page")

    plots_relative_dir = output_dir.as_posix()

    section_names = []
    for fig in figures:
        section = _infer_section_name(fig)
        if section not in section_names:
            section_names.append(section)

    sections = _render_sections(
        figures=figures,
        plots_relative_dir=plots_relative_dir,
    )

    template = template_path.read_text()

    rendered = (
        template
        .replace("{{ page_title }}", html.escape(page_title))
        .replace("{{ sections }}", sections)
    )

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(rendered)

    log.info("Saved HTML report %s", output_html)