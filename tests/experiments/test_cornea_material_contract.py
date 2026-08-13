from tools.experiments.cornea_material_contract import wet_cornea_contract


def test_wet_cornea_contract_uses_visible_dielectric_reflection_without_alpha_fade():
    cfg = wet_cornea_contract()

    assert abs(cfg['ior'] - 1.376) < 1e-9
    assert 0.0 <= cfg['roughness'] <= 0.02
    assert 1.0 <= cfg['fresnel_boost'] <= 1.5
    assert cfg['transparent_base'] is True
    assert cfg['alpha_blending'] is False
    assert cfg['reflection_lobe'] == 'principled_metallic_white'


def test_wet_cornea_contract_is_deterministic_and_bounded():
    a = wet_cornea_contract()
    b = wet_cornea_contract()

    assert a == b
    assert a['roughness'] >= 0.005
    assert a['fresnel_boost'] > 0.0
