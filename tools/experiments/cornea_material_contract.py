def wet_cornea_contract():
    """Return the single bounded wet-cornea correction contract.

    The correction removes low-alpha shading attenuation and uses a
    Fresnel-weighted reflective lobe over a transparent base.  It is
    intentionally small and deterministic so the render gate tests one
    hypothesis only.
    """
    return {
        'ior': 1.376,
        'roughness': 0.012,
        'fresnel_boost': 1.35,
        'transparent_base': True,
        'alpha_blending': False,
        'reflection_lobe': 'principled_metallic_white',
    }
