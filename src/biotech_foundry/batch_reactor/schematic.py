"""Render the reactor's operator schematic from a single playback state."""
from .model import BatchReactor


def reactor_schematic(
    reactor: BatchReactor,
    measured_c: float,
    heater_w: float,
    loss_w: float,
    *,
    playing: bool,
) -> str:
    vessel = reactor.vessel
    level = vessel.liquid_height_m / vessel.height_m
    surface_y = 304 - 174 * level
    impeller_y = 304 - min(45, 87 * level)
    rpm = reactor.equipment.agitation_rpm
    heating = heater_w > 0
    mixing = rpm > 0
    heater_class = "active" if heating else "idle"
    motor_class = "active" if mixing else "idle"
    moving = " moving" if playing else ""
    ambient_direction = "outward" if loss_w >= 0 else "inward"
    ambient_class = "thermal" if abs(loss_w) >= 0.5 else "idle"
    ambient_marker = "marker-end" if loss_w >= 0 else "marker-start"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 402"
         role="img" aria-label="Batch reactor schematic. Heater {heater_w:.0f} watts.
         Agitator {rpm:.0f} RPM. Temperature transmitter {measured_c:.1f} degrees Celsius."
         style="display:block;width:100%;max-height:460px">
      <style>
        .reactor-diagram text {{font-family:system-ui,sans-serif;fill:#e2e8f0}}
        .reactor-diagram .label {{font-size:14px;font-weight:650;letter-spacing:1px}}
        .reactor-diagram .value {{font-size:18px;font-weight:650}}
        .reactor-diagram .muted {{font-size:13px;fill:#a8bdd0}}
        .reactor-diagram .path {{fill:none;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}}
        .reactor-diagram .idle {{stroke:#64748b}}
        .reactor-diagram .active {{stroke:#5ef59a;filter:drop-shadow(0 0 5px #2ed879)}}
        .reactor-diagram .signal {{stroke:#7dd3fc;stroke-dasharray:5 6}}
        .reactor-diagram .thermal {{stroke:#fbbf68;stroke-dasharray:5 6}}
        .reactor-diagram .trace {{stroke-dasharray:10 7}}
        .reactor-diagram .moving {{animation:reactor-dash .8s linear infinite}}
        @keyframes reactor-dash {{to {{stroke-dashoffset:-34}}}}
        @media (prefers-reduced-motion:reduce) {{.reactor-diagram .moving {{animation:none}}}}
      </style>
      <g class="reactor-diagram">
        <defs>
          <pattern id="reactor-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M24 0H0V24" fill="none" stroke="#1c3042" opacity=".65"/>
          </pattern>
          <clipPath id="reactor-shell"><rect x="270" y="121" width="220" height="195" rx="26"/></clipPath>
          <marker id="reactor-heat-arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4"
                  markerHeight="4" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#fbbf68"/></marker>
        </defs>
        <rect width="760" height="402" rx="16" fill="#101e2c"/>
        <rect x="1" y="1" width="758" height="400" rx="16" fill="url(#reactor-grid)" stroke="#30485d"/>

        <g clip-path="url(#reactor-shell)">
          <rect x="270" y="121" width="220" height="195" fill="#152c40"/>
          <rect x="270" y="{surface_y:.2f}" width="220" height="{316 - surface_y:.2f}" fill="#164c70"/>
          <path d="M270 {surface_y:.2f}H490" stroke="#62caff" stroke-width="2"/>
        </g>
        <rect x="270" y="121" width="220" height="195" rx="26" fill="none" stroke="#a6bfd4" stroke-width="3"/>

        <path d="M174 217H230V290H291" class="path {heater_class} trace{moving if heating else ''}"/>
        <path d="M291 290h16l9 -8 12 16 12 -16 12 16 12 -8h18" class="path {heater_class}"/>
        <rect x="41" y="184" width="133" height="64" rx="10" fill="#152b3b" class="{heater_class}"/>
        <text x="56" y="207" class="label">EH-201</text>
        <text x="56" y="230" class="value">{heater_w:,.0f} W</text>
        <text x="43" y="269" class="muted">Heater to water · {'ON' if heating else 'OFF'}</text>

        <rect x="351" y="44" width="58" height="50" rx="9" fill="#152b3b" class="{motor_class}"/>
        <text x="380" y="75" class="value" text-anchor="middle">M</text>
        <text x="425" y="65" class="label">M-201</text>
        <text x="425" y="86" class="muted">{rpm:,.0f} RPM setpoint</text>
        <path d="M380 94V{impeller_y:.2f}" class="path {motor_class}"/>
        <ellipse cx="380" cy="{impeller_y:.2f}" rx="40" ry="{min(11, 45 * level):.2f}"
                 class="path {motor_class} trace{moving if mixing else ''}"/>
        <path d="M360 {impeller_y:.2f}h40" class="path {motor_class}"/>

        <path d="M465 {surface_y + 5:.2f}H513V164H578" class="path signal"/>
        <circle cx="465" cy="{surface_y + 5:.2f}" r="5" fill="#7dd3fc"/>
        <circle cx="611" cy="164" r="33" fill="#172d40" stroke="#7dd3fc" stroke-width="2"/>
        <text x="611" y="169" class="label" text-anchor="middle">TT-201</text>
        <text x="611" y="221" class="value" text-anchor="middle">{measured_c:.1f} °C</text>
        <text x="611" y="242" class="muted" text-anchor="middle">Virtual transmitter</text>

        <path d="M491 283H572" class="path {ambient_class}"
              {ambient_marker + '="url(#reactor-heat-arrow)"' if ambient_class == 'thermal' else ''}/>
        <text x="588" y="280" class="label">AMBIENT</text>
        <text x="588" y="301" class="muted">{abs(loss_w):.0f} W {ambient_direction}</text>

        <text x="380" y="349" class="label" text-anchor="middle">R-201 · BATCH REACTOR</text>
        <text x="380" y="373" class="muted" text-anchor="middle">{vessel.working_volume_m3 * 1000:g} L water · {level:.0%} vessel fill</text>
      </g>
    </svg>
    """
