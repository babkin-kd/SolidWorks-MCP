"""Exact installed-wheel L3-I1 positive native case, not whole L3 acceptance.

Reuses the source probe's single CAD owner and full oracle. Wheel/origin/metadata
are checked before CAD; the report stays accepted=False because negative cases
and the public MCP chain are separate required gates.
"""
from probe_native_first_save_domain import main


if __name__ == '__main__':
    main(installed=True)
