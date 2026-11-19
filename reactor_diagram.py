"""Render the live jacket loop and reactor as a single P&ID view."""

from typing import Optional


def render_reactor_diagram(
    *,
    inlet_c: float,
    outlet_c: float,
    water_c: float,
    water_l: float,
    capacity_l: float,
    duty_w: float,
    ambient_w: float,
    rpm: int,
    playing: bool,
    circulating: bool,
    batch_mass_kg: Optional[float] = None,
    gross_mass_kg: Optional[float] = None,
) -> str:
    fill_fraction = min(0.95, max(0.05, water_l / capacity_l))
    vessel_bottom = 287
    water_height = 165 * fill_fraction
    surface_y = vessel_bottom - water_height

    inlet_path = "M46 162H221H390"
    outlet_path = "M666 223H872H1034"
    idle_color, heating_color, cooling_color = "#94a3b8", "#5ef59a", "#4cc9f0"
    flow_color = idle_color
    flow_track = "pid-flow-track"
    flow_animation = ""
    flow_status = "Jacket circulation stopped."
    if playing and circulating:
        flow_status = "Jacket fluid circulating."
        # The pipes show the supply condition even as jacket hold-up catches up.
        supply_delta_c = inlet_c - water_c
        if supply_delta_c > 0.05:
            flow_color = heating_color
        elif supply_delta_c < -0.05:
            flow_color = cooling_color
        flow_track += " is-moving"
        flow_animation = (
            f'<path class="pid-line pid-flow-dashes" d="{inlet_path} {outlet_path}" '
            f'stroke="{flow_color}" stroke-width="4"/>'
        )

    if abs(duty_w) <= 1:
        direction, duty_color = "Idle", idle_color
        duty_value = "0 W"
    else:
        direction, duty_color = ("Heating", heating_color) if duty_w > 0 else ("Cooling", cooling_color)
        duty_value = f"{duty_w:+.0f} W"

    ambient_color = "#fbbf68" if abs(ambient_w) >= 0.5 else "#94a3b8"
    ambient_path = "M646 275H801" if ambient_w >= 0 else "M801 275H646"
    ambient_marker = 'marker-end="url(#pid-ambient-arrow)"' if abs(ambient_w) >= 0.5 else ""
    ambient_reading = "0 W"
    if ambient_marker:
        ambient_direction = "outward" if ambient_w > 0 else "inward"
        ambient_reading = f"{abs(ambient_w):.0f} W {ambient_direction}"

    impeller_class = "pid-line pid-impeller"
    motor_color = idle_color
    if playing and rpm:
        impeller_class += " is-moving"
        motor_color = heating_color

    duty_label = f"{direction} · {duty_value}" if direction != "Idle" else f"Batch duty · {duty_value}"

    scale_signal = ""
    mass_status = ""
    vessel_basis = (
        f'<text x="528" y="334" class="pid-secondary" text-anchor="middle">'
        f'{water_l:.0f} L / {capacity_l:.0f} L vessel basis</text>'
    )
    if batch_mass_kg is not None and gross_mass_kg is not None:
        # Keep the volume caption in a separate column from the support pads.
        vessel_basis = (
            f'<text x="1034" y="337" class="pid-secondary" text-anchor="end">'
            f'Fill · {water_l:.0f} / {capacity_l:.0f} L</text>'
        )
        mass_status = (
            f" WT-201 reports {batch_mass_kg:,.1f} kilograms net "
            f"and {gross_mass_kg:,.1f} kilograms gross."
        )
        scale_signal = f"""
      <path class="pid-line" d="M82 306V317H425" stroke="#c4b5fd" stroke-width="2.5" stroke-dasharray="4 6"/>
      <g class="pid-load-cells" stroke="#c4b5fd" stroke-linejoin="round">
        <path d="M437 307V313 M619 307V313" stroke-width="4"/>
        <rect x="425" y="312" width="24" height="10" rx="3" fill="#221e3d" stroke-width="2"/>
        <rect x="607" y="312" width="24" height="10" rx="3" fill="#221e3d" stroke-width="2"/>
        <path d="M421 323H453 M603 323H635" stroke-width="2"/>
      </g>
      <circle cx="82" cy="270" r="36" fill="#221e3d" stroke="#c4b5fd" stroke-width="2"/>
      <text x="82" y="277" class="pid-instrument" text-anchor="middle">WT-201</text>
      <text x="134" y="259" class="pid-value">{batch_mass_kg:,.1f} kg net</text>
      <text x="134" y="288" class="pid-secondary">Gross {gross_mass_kg:,.1f} kg</text>
      """

    return f"""<svg xmlns="http://www.w3.org/2000/svg" class="reactor-pid"
      viewBox="0 0 1080 370" preserveAspectRatio="xMidYMid meet" role="img"
      aria-label="R-201 jacketed batch reactor, {direction.lower()}. Jacket inlet {inlet_c:.1f} °C,
      outlet {outlet_c:.1f} °C and reactor water {water_c:.1f} °C. {flow_status}{mass_status}">
      <style>
        .reactor-pid text {{
          fill: #f1f5f9;
          font-family: system-ui, sans-serif;
          font-variant-numeric: tabular-nums;
        }}
        .reactor-pid .pid-title {{ font-size: 24px; font-weight: 700; }}
        .reactor-pid .pid-tag {{ font-size: 21px; font-weight: 650; }}
        .reactor-pid .pid-instrument {{ font-size: 18px; font-weight: 700; }}
        .reactor-pid .pid-value {{ font-size: 28px; font-weight: 650; }}
        .reactor-pid .pid-secondary {{ font-size: 19px; fill: #becfe0; }}
        .reactor-pid .pid-duty {{ font-size: 21px; font-weight: 650; fill: {duty_color}; }}
        .reactor-pid .pid-line {{
          fill: none;
          stroke-linecap: round;
          stroke-linejoin: round;
        }}
        .reactor-pid .pid-flow-track.is-moving {{ stroke-opacity: .35; }}
        .reactor-pid .pid-flow-dashes, .reactor-pid .pid-impeller.is-moving {{
          stroke-dasharray: 14 8;
          animation: reactor-flow-dash .8s linear infinite;
        }}
        @keyframes reactor-flow-dash {{ to {{ stroke-dashoffset: -44; }} }}
        @media (prefers-reduced-motion: reduce) {{
          .reactor-pid .pid-flow-dashes, .reactor-pid .pid-impeller.is-moving {{ animation: none; }}
        }}
      </style>
      <defs>
        <clipPath id="pid-vessel">
          <rect x="410" y="122" width="236" height="165" rx="26"/>
        </clipPath>
        <marker id="pid-flow-arrow" markerUnits="userSpaceOnUse" markerWidth="14" markerHeight="12"
          viewBox="0 0 14 12" refX="7" refY="6" orient="auto">
          <path d="M0 0L14 6L0 12Z" fill="{flow_color}"/>
        </marker>
        <marker id="pid-ambient-arrow" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="10"
          viewBox="0 0 12 10" refX="11" refY="5" orient="auto">
          <path d="M0 0L12 5L0 10Z" fill="{ambient_color}"/>
        </marker>
      </defs>

      <text x="540" y="40" class="pid-title" text-anchor="middle">R-201 · Jacketed batch reactor</text>

      <rect x="390" y="105" width="276" height="199" rx="36" fill="none"
        stroke="#718096" stroke-width="9"/>
      <g clip-path="url(#pid-vessel)">
        <rect x="410" y="{surface_y:.1f}" width="236" height="{water_height:.1f}" fill="#164c70"/>
        <path d="M410 {surface_y:.1f}H646" stroke="#62caff" stroke-width="2"/>
      </g>
      <rect x="410" y="122" width="236" height="165" rx="26" fill="none"
        stroke="#b7cfdf" stroke-width="4"/>

      <path class="pid-line {flow_track}" d="{inlet_path}" stroke="{flow_color}" stroke-width="4"
        marker-mid="url(#pid-flow-arrow)"/>
      <path class="pid-line {flow_track}" d="{outlet_path}" stroke="{flow_color}" stroke-width="4"
        marker-mid="url(#pid-flow-arrow)"/>
      {flow_animation}
      <text x="46" y="106" class="pid-tag">Jacket inlet · actual</text>
      <text x="46" y="143" class="pid-value">{inlet_c:.1f} °C</text>
      <text x="1034" y="202" class="pid-tag" text-anchor="end">Jacket outlet · {outlet_c:.1f} °C</text>

      <rect x="498" y="57" width="60" height="44" rx="9" fill="#152b3b"
        stroke="{motor_color}" stroke-width="1.5"/>
      <text x="528" y="87" class="pid-tag" text-anchor="middle">M</text>
      <text x="574" y="76" class="pid-tag">M-201</text>
      <text x="574" y="99" class="pid-secondary">{rpm} RPM setpoint</text>
      <path class="pid-line" d="M528 101V257 M499 257H557" stroke="{motor_color}" stroke-width="4"/>
      <ellipse cx="528" cy="257" rx="42" ry="11" class="{impeller_class}" stroke="{motor_color}"
        stroke-width="4"/>

      <path class="pid-line" d="M646 172H728V109H771" stroke="#7dd3fc" stroke-width="3"
        stroke-dasharray="5 6"/>
      <circle cx="808" cy="109" r="37" fill="#172d40" stroke="#7dd3fc" stroke-width="2"/>
      <text x="808" y="116" class="pid-instrument" text-anchor="middle">TT-201</text>
      <text x="863" y="106" class="pid-value">{water_c:.1f} °C</text>
      <text x="863" y="133" class="pid-secondary">Reactor water</text>

      <path class="pid-line" d="{ambient_path}" stroke="{ambient_color}" stroke-width="3"
        stroke-dasharray="5 6" {ambient_marker}/>
      <text x="820" y="269" class="pid-tag">Ambient</text>
      <text x="820" y="294" class="pid-secondary">{ambient_reading}</text>

      {scale_signal}
      {vessel_basis}
      <text x="528" y="359" class="pid-duty" text-anchor="middle">{duty_label}</text>
    </svg>"""
