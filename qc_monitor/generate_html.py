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

    if name.startswith("vis_bias") or name.startswith("vis_master_ron") or "VIS Bias" in title or "VIS Master RON" in title:
        return "VIS Bias"

    if name.startswith("vis_flat") or "VIS Flat" in title:
        return "VIS Flat"

    if name.startswith("nir_dark") or "NIR Dark" in title:
        return "NIR Dark"

    if name.startswith("nir_flat") or "NIR Flat" in title:
        return "NIR Flat"

    return "Other QC Plots"


def _render_navigation(section_names: list[str]) -> str:
    return "\n".join(
        f'  <a href="#{_slugify(section)}">{html.escape(section)}</a>'
        for section in section_names
    )


def _render_sections(figures: list[dict], plots_relative_dir: str) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)

    for fig in figures:
        grouped[_infer_section_name(fig)].append(fig)

    html_sections = []

    for section_name, section_figures in grouped.items():
        section_id = _slugify(section_name)

        section_html = [
            f'  <section id="{section_id}">',
            f"    <h2>{html.escape(section_name)}</h2>",
            "",
        ]

        for fig in section_figures:
            title = fig.get("title", fig.get("name", "Untitled plot"))
            filename = fig["filename"]
            img_path = f"{plots_relative_dir}/{filename}"

            safe_title = html.escape(title)
            safe_img_path = html.escape(img_path, quote=True)

            section_html.extend(
                [
                    '    <div class="plot-card">',
                    f"      <h3>{safe_title}</h3>",
                    f'      <a href="{safe_img_path}">',
                    f'        <img src="{safe_img_path}" alt="{safe_title}">',
                    "      </a>",
                    "    </div>",
                    "",
                ]
            )

        section_html.append("  </section>")
        html_sections.append("\n".join(section_html))

    return "\n\n".join(html_sections)


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

    navigation = _render_navigation(section_names)
    sections = _render_sections(
        figures=figures,
        plots_relative_dir=plots_relative_dir,
    )

    template = template_path.read_text()

    rendered = (
        template
        .replace("{{ page_title }}", html.escape(page_title))
        .replace("{{ navigation }}", navigation)
        .replace("{{ sections }}", sections)
    )

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(rendered)

    log.info("Saved HTML report %s", output_html)