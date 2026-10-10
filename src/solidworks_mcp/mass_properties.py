"""Validate SI measurements before returning finite, explicitly converted values."""

import math
from numbers import Real

from .documents import rejected


def normalize_mass_properties(values):
    def number(value, *, positive=False):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise rejected('mass_properties_invalid', 'Mass properties contain a non-numeric value.')
        value = float(value)
        if not math.isfinite(value) or (positive and value <= 0):
            raise rejected('mass_properties_invalid', 'Mass properties must be finite; solid measures must be positive.')
        return value

    try:
        volume = number(values['volume_m3'], positive=True)
        area = number(values['surface_area_m2'], positive=True)
        mass = number(values['mass_kg'], positive=True)
        density = number(values['density_kg_m3'], positive=True)
        center = values['center_of_mass_m']
        if not isinstance(center, (list, tuple)) or len(center) != 3:
            raise rejected('mass_properties_invalid', 'Center of mass must contain three model coordinates.')
        if not math.isclose(mass, density * volume, rel_tol=1e-6, abs_tol=0):
            raise rejected('mass_properties_inconsistent', 'Mass, effective density and volume do not agree.')
        return {'volume_mm3': number(volume * 1e9, positive=True),
                'surface_area_mm2': number(area * 1e6, positive=True),
                'mass_kg': mass, 'density_kg_m3': density,
                'center_of_mass_mm': [number(number(v) * 1000) for v in center]}
    except (KeyError, TypeError, OverflowError) as exc:
        raise rejected('mass_properties_invalid', 'SolidWorks mass properties are incomplete or invalid.') from exc
