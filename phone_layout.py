"""Compact operator displays using readings from the existing simulator models."""
from html import escape
from pathlib import Path

import streamlit as st


def phone_view():
    # The Studio passes the layout for narrow embeds. Direct phone visits use
    # the same view, including when Streamlit is opened outside the Studio.
    agent = st.context.headers.get("User-Agent", "").lower()
    return st.query_params.get("view") == "phone" or any(
        part in agent for part in ("iphone", "ipod", "android", "mobile")
    )


def settings_panel(label, compact):
    if compact:
        st.html(Path(__file__).with_name("phone_layout.css"))
        return st.expander(label, icon=":material/tune:")
    return st.sidebar


def transfer_display(source_l, destination_l, source_pct, destination_pct, flow_lpm, active):
    """Trace the same bottom outlet and top inlet as the desktop process graphic."""
    def vessel(x, y, name, liters, percent):
        fill = 55 * max(0, min(100, percent)) / 100
        return f"""
        <rect class="shell" x="{x}" y="{y}" width="98" height="59" rx="8"/>
        <clipPath id="clip-{name}"><rect x="{x+2}" y="{y+2}" width="94" height="55" rx="6"/></clipPath>
        <rect class="water" x="{x+2}" y="{y+57-fill:.2f}" width="94" height="{fill:.2f}" clip-path="url(#clip-{name})"/>
        <text class="tag" x="{x+49}" y="{y+77 if name == 'Destination' else y-9}">{name}</text>
        <text class="value" x="{x+49}" y="{y+28}">{liters:,.1f} L</text>
        <text x="{x+49}" y="{y+48}">{percent:.0f}% full</text>"""
    svg = f"""
      <svg class="phone-process" viewBox="0 0 320 174" role="img"
           aria-label="Source {source_l:.1f} liters, destination {destination_l:.1f} liters.">
        <path class="pipe{' flowing' if active else ''}" d="M66 119V144H175V12H255V45"/>
        {vessel(17,59,"Source",source_l,source_pct)}
        {vessel(206,45,"Destination",destination_l,destination_pct)}
        <circle class="pump{' on' if active else ''}" cx="122" cy="144" r="13"/>
        <path d="m118 138 11 6-11 6z" fill="#eaf5f6"/>
        <path d="m250 35 5 7 5-7" fill="none" stroke="#9bbec4" stroke-width="2.5"/>
        <text x="250" y="138">{flow_lpm:.1f} L/min</text>
        <text class="small" x="250" y="157">Pump operating point</text>
      </svg>"""
    markup = " ".join(line.strip() for line in svg.splitlines())
    st.markdown(f"<div>{markup}</div>", unsafe_allow_html=True)


def thermal_display(*, water_l, capacity_l, temp_c, first, second):
    """Group the live vessel level and its two equipment readings at phone size."""
    fill_pct = max(0, min(100, 100 * water_l / capacity_l))
    items = "".join(
        f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"
        for label, value in (first, second)
    )
    st.html(f"""
      <div class="phone-thermal">
        <div class="phone-vessel" style="--fill:{fill_pct:.2f}%">
          <span>Reactor water</span><strong>{temp_c:.1f} °C</strong><span>{water_l:g} L</span>
        </div>
        <dl>{items}</dl>
      </div>""")
