import pytest

from backend.src.services.apca import apca_contrast, srgb_to_y


class TestApcaCalculator:
    def test_srgb_to_y_black_white(self):
        y_black = srgb_to_y(0, 0, 0)
        y_white = srgb_to_y(255, 255, 255)
        assert pytest.approx(y_black) == 0.0
        assert pytest.approx(y_white) == 1.0

    def test_apca_contrast_extremes(self):
        # White text on Black background (WoB - negative polarity)
        y_txt_white = srgb_to_y(255, 255, 255)
        y_bg_black = srgb_to_y(0, 0, 0)
        contrast_wob = apca_contrast(y_txt_white, y_bg_black)

        # Black text on White background (BoW - positive polarity)
        y_txt_black = srgb_to_y(0, 0, 0)
        y_bg_white = srgb_to_y(255, 255, 255)
        contrast_bow = apca_contrast(y_txt_black, y_bg_white)

        # White on Black Lc score should be negative and around -106 to -108
        assert contrast_wob < -100
        # Black on White Lc score should be positive and around 105 to 107
        assert contrast_bow > 100

    def test_apca_contrast_same_color(self):
        y_txt = srgb_to_y(128, 128, 128)
        y_bg = srgb_to_y(128, 128, 128)
        assert apca_contrast(y_txt, y_bg) == 0.0

    def test_apca_contrast_low_contrast(self):
        y_txt = srgb_to_y(254, 254, 254)
        y_bg = srgb_to_y(255, 255, 255)
        assert apca_contrast(y_txt, y_bg) == 0.0
