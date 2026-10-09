import html
import logging
from importlib import resources
from collections import defaultdict
from pathlib import Path

from .figure_result import validate_figure_results

log = logging.getLogger(__name__)


def _load_template(template_path: Path | None) -> str:
    if template_path is not None:
        try:
            return Path(template_path).read_text()
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Configured HTML template not found: {template_path}"
            ) from exc

    try:
        return (
            resources.files("qc_monitor")
            .joinpath("resources", "template.html")
            .read_text()
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Bundled HTML template not found. Reinstall qc-monitor with "
            "`pip install .` from the repository root."
        ) from exc


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
    if 'arm' in figure:
        return figure['arm']
    name = figure.get("name", "").lower()
    title = figure.get("title", "")

    if name.startswith("vis_") or title.startswith("VIS"):
        return "VIS"

    if name.startswith("nir_") or title.startswith("NIR"):
        return "NIR"

    return "OTHER"


def _render_sections(figures: list[dict], plots_relative_dir: str, figure_results=None,
                     image_urls=None) -> str:
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
            section_id = html.escape(_slugify(f"{arm}-{section_name}"), quote=True)

            chunks.extend([
                f'  <section id="{section_id}">',
                f"    <h2>{html.escape(section_name)}</h2>",
                '    <div class="plot-grid">',
                "",
            ])

            for fig in section_figures:
                title = fig.get("title", fig.get("name", "Untitled plot"))
                filename = fig["filename"]
                img_path = (image_urls[fig['name']] if image_urls is not None
                            and fig['name'] in image_urls else f"{plots_relative_dir}/{filename}")

                wide = fig.get("wide", False)
                card_class = "plot-card wide" if wide else "plot-card"

                safe_title = html.escape(title)
                safe_img_path = html.escape(img_path, quote=True)

                result = figure_results.get(fig['name']) if figure_results is not None else None
                chunks.extend([f'    <div class="{card_class}">', f'      <h3>{safe_title}</h3>'])
                if result is not None:
                    labels = {'produced': 'Produced', 'no_data': 'No data', 'failed': 'Failed',
                              'reused': 'Reused after failure'}
                    chunks.append(f'      <p class="figure-state {result.state}">{labels[result.state]}: '
                                  f'{html.escape(result.reason)}</p>')
                    if result.state == 'reused':
                        chunks.append('      <p class="figure-warning">Original image produced (UTC): '
                                      f'{html.escape(result.generated_utc)}</p>')
                    for discarded in result.discarded:
                        message = (f"Discarded {discarded['count']} sample(s) — "
                                   f"{discarded['context']}: {discarded['reason']}")
                        chunks.append(f'      <p class="figure-warning">{html.escape(message)}</p>')
                if result is None or result.state in ('produced', 'reused'):
                    chunks.extend([f'      <a href="{safe_img_path}">',
                                   f'        <img src="{safe_img_path}" alt="{safe_title}">',
                                   '      </a>'])
                chunks.extend(['    </div>', ''])

            chunks.append("    </div>")
            chunks.append("  </section>")

        chunks.append("</div>")
        return "\n".join(chunks)

    return "\n\n".join([
        render_arm_tab("VIS", active=True),
        render_arm_tab("NIR", active=False),
    ])


def _render_html_report(
    plots_cfg: dict,
    output_html: Path,
    template_path: Path | None = None,
    figure_results=None,
    *,
    image_urls=None,
):
    figures = plots_cfg.get("figures", [])
    outcomes = (validate_figure_results(figures, figure_results)
                if figure_results is not None else None)

    if not figures:
        log.info("No figures configured, skipping HTML report generation")
        return

    page_title = plots_cfg.get("page_title", "SOXS Quality Control Page")

    # plots folder is expected to be relative to the output HTML file
    plots_relative_dir = Path("plots").as_posix()

    section_names = []
    for fig in figures:
        section = _infer_section_name(fig)
        if section not in section_names:
            section_names.append(section)

    sections = _render_sections(
        figures=figures,
        plots_relative_dir=plots_relative_dir,
        figure_results=outcomes,
        image_urls=image_urls,
    )

    template = _load_template(template_path)

    rendered = (
        template
        .replace("{{ page_title }}", html.escape(page_title))
        .replace("{{ sections }}", sections)
    )

    return rendered


def generate_html_report(
    plots_cfg: dict,
    output_html: Path,
    template_path: Path | None = None,
    figure_results=None,
    *,
    image_urls=None,
):
    rendered = _render_html_report(plots_cfg, output_html, template_path,
                                   figure_results, image_urls=image_urls)
    if rendered is None:
        return
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(rendered)

    log.info("Saved HTML report %s", output_html)
