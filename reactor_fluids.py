"""Temperature-dependent inhibited glycol/water data for the educational simulator.

Rows are temperature (°C), density (kg/m³), specific heat (J/kg·K),
thermal conductivity (W/m·K), and dynamic viscosity (mPa·s).
PG: Dow DOWFROST Engineering and Operating Guide, Tables 10, 14, 18, 22.
https://ingredi.com/content/pdfs/DOWFROST_Manual.pdf
EG: Dow DOWTHERM SR-1 Engineering and Operating Guide, Tables 11, 15, 19, 23.
https://www.magnumsolvent.com/productdata/Product%20Literature/Heat%20Transfer%20Fluids/Engineering%20%26%20Operating%20Guide%20-%20DOWTHERM%20SR-1.pdf
Concentrations are volume percentages of glycol, not of commercial concentrate.
"""

from bisect import bisect_right
from dataclasses import dataclass
from math import exp, log
from typing import Optional


_PG_CURVES = {
    20: (
        (-5, 1028.4, 3918, 0.449, 4.98),
        (0, 1027, 3929, 0.456, 4.05),
        (10, 1023.8, 3951, 0.470, 2.79),
        (20, 1020.2, 3973, 0.483, 2.02),
        (40, 1011.3, 4016, 0.505, 1.18),
        (60, 1000.4, 4060, 0.521, 0.78),
        (80, 987.5, 4104, 0.533, 0.56),
        (100, 972.7, 4147, 0.540, 0.43),
    ),
    30: (
        (-10, 1040.6, 3765, 0.397, 11.84),
        (-5, 1039.1, 3779, 0.403, 9.07),
        (0, 1037.4, 3793, 0.409, 7.07),
        (10, 1033.7, 3820, 0.421, 4.52),
        (20, 1029.5, 3848, 0.431, 3.06),
        (40, 1019.6, 3903, 0.450, 1.63),
        (60, 1007.6, 3958, 0.463, 1.01),
        (80, 993.5, 4013, 0.473, 0.70),
        (100, 977.5, 4068, 0.478, 0.53),
    ),
    40: (
        (-20, 1053.1, 3569, 0.346, 48.90),
        (-15, 1051.6, 3586, 0.351, 33.07),
        (-10, 1050, 3603, 0.356, 23.11),
        (-5, 1048.2, 3619, 0.361, 16.63),
        (0, 1046.3, 3636, 0.366, 12.30),
        (10, 1042.1, 3669, 0.376, 7.21),
        (20, 1037.4, 3702, 0.384, 4.59),
        (40, 1026.4, 3768, 0.399, 2.24),
        (60, 1013.4, 3834, 0.410, 1.31),
        (80, 998.4, 3900, 0.418, 0.88),
        (100, 981.2, 3966, 0.422, 0.65),
    ),
    50: (
        (-20, 1061.7, 3378, 0.311, 72.42),
        (-15, 1059.9, 3397, 0.315, 49.29),
        (-10, 1058, 3416, 0.319, 34.51),
        (-5, 1056, 3435, 0.323, 24.81),
        (0, 1053.9, 3455, 0.327, 18.28),
        (10, 1049.2, 3493, 0.334, 10.59),
        (20, 1044, 3532, 0.341, 6.62),
        (40, 1032.1, 3609, 0.353, 3.10),
        (60, 1018.2, 3686, 0.362, 1.75),
        (80, 1002.2, 3763, 0.367, 1.12),
        (100, 984.1, 3841, 0.370, 0.79),
    ),
    60: (
        (-20, 1068.9, 3162, 0.278, 137.96),
        (-15, 1066.9, 3184, 0.282, 92.00),
        (-10, 1064.8, 3206, 0.285, 62.78),
        (-5, 1062.6, 3228, 0.288, 43.84),
        (0, 1060.2, 3250, 0.291, 31.32),
        (10, 1055.1, 3295, 0.297, 17.05),
        (20, 1049.4, 3339, 0.302, 10.04),
        (40, 1036.6, 3427, 0.311, 4.25),
        (60, 1021.8, 3515, 0.317, 2.22),
        (80, 1004.9, 3603, 0.321, 1.35),
        (100, 986, 3692, 0.323, 0.92),
    ),
}

_EG_CURVES = {
    20: (
        (-5, 1038, 3759, 0.458, 3.65),
        (0, 1036.8, 3771, 0.466, 3.02),
        (10, 1034.1, 3794, 0.479, 2.18),
        (25, 1029.1, 3828, 0.498, 1.46),
        (40, 1023, 3862, 0.514, 1.06),
        (60, 1013.1, 3908, 0.530, 0.74),
        (80, 1001.3, 3954, 0.542, 0.55),
        (100, 987.6, 4000, 0.549, 0.43),
    ),
    30: (
        (-15, 1056.6, 3548, 0.405, 7.77),
        (-10, 1055.5, 3562, 0.411, 6.19),
        (-5, 1054.3, 3576, 0.417, 5.03),
        (0, 1053, 3590, 0.423, 4.15),
        (10, 1049.9, 3619, 0.435, 2.95),
        (25, 1044.5, 3661, 0.450, 1.92),
        (40, 1037.9, 3704, 0.463, 1.34),
        (60, 1027.5, 3761, 0.477, 0.90),
        (80, 1015.1, 3817, 0.487, 0.65),
        (100, 1000.8, 3874, 0.493, 0.49),
    ),
    40: (
        (-20, 1073.2, 3335, 0.366, 15.75),
        (-15, 1072.1, 3352, 0.371, 11.74),
        (-10, 1070.8, 3369, 0.376, 9.06),
        (-5, 1069.5, 3386, 0.381, 7.18),
        (0, 1068, 3403, 0.386, 5.83),
        (10, 1064.7, 3436, 0.395, 4.04),
        (25, 1058.8, 3486, 0.408, 2.57),
        (40, 1051.8, 3537, 0.419, 1.77),
        (60, 1040.8, 3604, 0.430, 1.17),
        (80, 1027.8, 3671, 0.438, 0.82),
        (100, 1012.9, 3738, 0.442, 0.60),
    ),
    50: (
        (-20, 1088.1, 3128, 0.336, 22.07),
        (-15, 1086.8, 3147, 0.340, 16.53),
        (-10, 1085.4, 3166, 0.344, 12.74),
        (-5, 1083.9, 3185, 0.348, 10.05),
        (0, 1082.3, 3205, 0.352, 8.09),
        (10, 1078.7, 3243, 0.360, 5.50),
        (25, 1072.3, 3301, 0.370, 3.39),
        (40, 1064.9, 3359, 0.378, 2.26),
        (60, 1053.2, 3437, 0.387, 1.43),
        (80, 1039.6, 3514, 0.394, 0.98),
        (100, 1024.1, 3591, 0.397, 0.70),
    ),
    60: (
        (-20, 1102.3, 2911, 0.310, 34.28),
        (-15, 1100.9, 2933, 0.313, 25.69),
        (-10, 1099.3, 2954, 0.316, 19.62),
        (-5, 1097.7, 2976, 0.319, 15.25),
        (0, 1095.9, 2998, 0.322, 12.05),
        (10, 1091.9, 3042, 0.328, 7.85),
        (25, 1085.1, 3107, 0.336, 4.52),
        (40, 1077.2, 3172, 0.343, 2.84),
        (60, 1064.9, 3260, 0.350, 1.69),
        (80, 1050.7, 3347, 0.355, 1.10),
        (100, 1034.5, 3434, 0.357, 0.77),
    ),
}


@dataclass(frozen=True)
class FluidProperties:
    density: float
    cp: float
    conductivity: float
    viscosity: float


@dataclass(frozen=True)
class Fluid:
    label: str
    concentration: Optional[int]
    density: float
    cp: float
    conductivity: float
    viscosity: float
    note: str

    @property
    def minimum_liquid_c(self) -> float:
        """Lowest modeled command, with the table floor and a 3 °C freeze margin."""
        if self.concentration is None:
            return -20.0
        curve, freezing = _profile(self.label, self.concentration)
        return max(curve[0][0], round(freezing + 3.0, 1))

    def at_temperature(self, temp_c: float) -> FluidProperties:
        """Interpolate the measured table and hold its end values outside the grid.

        Viscosity interpolates in log space and is returned in Pa·s. A temperature
        with tabulated properties is not necessarily an approved operating point.
        The generic 10 cSt PDMS example retains its room-temperature assumptions.
        """
        if self.concentration is None:
            return FluidProperties(self.density, self.cp, self.conductivity, self.viscosity)
        curve, _ = _profile(self.label, self.concentration)
        return _interpolate(curve, temp_c)


def _interpolate(curve, temp_c):
    index = bisect_right(curve, (temp_c, float("inf")))
    if index == 0 or index == len(curve):
        _, density, cp, conductivity, viscosity = curve[0 if index == 0 else -1]
        return FluidProperties(density, cp, conductivity, viscosity / 1000)

    low, high = curve[index - 1], curve[index]
    fraction = (temp_c - low[0]) / (high[0] - low[0])
    density, cp, conductivity = (
        a + fraction * (b - a) for a, b in zip(low[1:4], high[1:4])
    )
    viscosity = low[4] * exp(fraction * log(high[4] / low[4])) / 1000
    return FluidProperties(density, cp, conductivity, viscosity)


_PG_LABEL = "Propylene glycol / water"
_EG_LABEL = "Ethylene glycol / water"
_PDMS_LABEL = "Polydimethylsiloxane (PDMS) thermal fluid"
# Dow's freeze tables interpolated to the offered volume fractions. For EG60
# the listed 57.8% vol freeze point is used as a conservative basis.
_FREEZE_PG_C = {20: -7.4, 30: -13.1, 40: -21.5, 50: -33.7, 60: -51.1}
_FREEZE_EG_C = {20: -8.9, 30: -15.9, 40: -24.9, 50: -37.2, 60: -48.3}


def _profile(label, concentration):
    if label == _PG_LABEL and concentration in _PG_CURVES:
        return _PG_CURVES[concentration], _FREEZE_PG_C[concentration]
    if label == _EG_LABEL and concentration in _EG_CURVES:
        return _EG_CURVES[concentration], _FREEZE_EG_C[concentration]
    raise ValueError("Choose a supported fluid and glycol concentration (20 to 60% by volume).")


def fluid_properties(label: str, concentration: Optional[int]) -> Fluid:
    if label == _PDMS_LABEL:
        if concentration is not None:
            raise ValueError("PDMS does not use a glycol concentration selection.")
        return Fluid(
            label, concentration, 935, 1500, .15, .0094,
            "Representative 10 cSt PDMS, with constant illustrative properties. Check the actual grade.",
        )
    curve, freezing = _profile(label, concentration)
    props = _interpolate(curve, 20.0)
    note = f"Approx. freezing point {freezing:g} °C. The model requires a 3 °C margin and available property data."
    if label == _EG_LABEL and concentration == 60:
        note = "Conservative freeze basis −48.3 °C (57.8% EG by volume). The modeled table ends at −20 °C."
    return Fluid(label, concentration, props.density, props.cp, props.conductivity, props.viscosity, note)
