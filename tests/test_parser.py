import unittest
from pathlib import Path

from osu_skill_profiler.parser.model import Beatmap
from osu_skill_profiler.parser.osu_parser import OsuParseError, effective_timing, parse_osu, parse_osu_file

FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_minimal_metadata_and_difficulty(self):
        beatmap = parse_osu_file(FIXTURES / "minimal.osu")
        self.assertEqual(beatmap.format_version, 14)
        self.assertEqual(beatmap.mode, 0)
        self.assertEqual(beatmap.metadata["BeatmapID"], 1000001)
        self.assertEqual(beatmap.metadata["BeatmapSetID"], 2000001)
        self.assertEqual(beatmap.metadata["Creator"], "fixture-mapper")
        self.assertEqual(beatmap.metadata["Version"], "Normal")
        self.assertEqual(beatmap.difficulty["ApproachRate"], 9.0)
        self.assertEqual(beatmap.difficulty["SliderMultiplier"], 1.8)
        self.assertEqual(beatmap.difficulty["SliderTickRate"], 1.0)

    def test_object_types(self):
        beatmap = parse_osu_file(FIXTURES / "minimal.osu")
        self.assertEqual([obj.object_type for obj in beatmap.hit_objects], ["circle", "circle", "slider", "spinner", "circle"])

    def test_slider_and_spinner_fields(self):
        beatmap = parse_osu_file(FIXTURES / "minimal.osu")
        slider = beatmap.hit_objects[2]
        self.assertEqual(slider.slider_curve_type, "B")
        self.assertEqual(len(slider.slider_points), 2)
        self.assertEqual(slider.slider_slides, 1)
        self.assertEqual(slider.slider_pixel_length, 180.0)
        spinner = beatmap.hit_objects[3]
        self.assertEqual(spinner.spinner_end_ms, 4000.0)

    def test_parse_is_deterministic(self):
        text = (FIXTURES / "sliders.osu").read_text(encoding="utf-8")
        first = parse_osu(text)
        second = parse_osu(text)
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(first.difficulty, second.difficulty)
        self.assertEqual(first.timing_points, second.timing_points)
        self.assertEqual(first.hit_objects, second.hit_objects)

    def test_crlf_parses_identically(self):
        text = (FIXTURES / "minimal.osu").read_text(encoding="utf-8")
        lf = parse_osu(text)
        crlf = parse_osu(text.replace("\n", "\r\n"))
        self.assertEqual(lf.hit_objects, crlf.hit_objects)
        self.assertEqual(lf.timing_points, crlf.timing_points)

    def test_missing_header_raises(self):
        with self.assertRaises(OsuParseError):
            parse_osu("[Metadata]\nTitle:X\n[HitObjects]\n64,64,1000,1,0")

    def test_malformed_slider_raises(self):
        text = "osu file format v14\n[HitObjects]\n64,64,1000,2,0,no-curve,1,100"
        with self.assertRaises(OsuParseError):
            parse_osu(text)

    def test_mania_object_rejected(self):
        text = "osu file format v14\n[HitObjects]\n64,64,1000,128,0"
        with self.assertRaises(OsuParseError):
            parse_osu(text)

    def test_timing_bpm_changes_and_sv(self):
        beatmap = parse_osu_file(FIXTURES / "timing_changes.osu")
        self.assertEqual(effective_timing(beatmap.timing_points, 1000.0)[:2], (120.0, 1.0))
        self.assertEqual(effective_timing(beatmap.timing_points, 2000.0)[:2], (120.0, 1.0))
        self.assertEqual(effective_timing(beatmap.timing_points, 5000.0)[:2], (240.0, 1.0))
        self.assertEqual(effective_timing(beatmap.timing_points, 6000.0)[:2], (240.0, 0.5))

    def test_effective_timing_before_first_point(self):
        beatmap = parse_osu_file(FIXTURES / "timing_changes.osu")
        bpm, sv, beat_length = effective_timing(beatmap.timing_points, 0.0)
        self.assertEqual((bpm, sv), (120.0, 1.0))
        self.assertEqual(beat_length, 500.0)

    def test_legacy_short_timing_line_defaults_to_red(self):
        # v3-era files sometimes store timing points with only time and beat
        # length; trailing fields default (meter=4, uninherited inferred from
        # the beat length sign).
        text = (
            "osu file format v3\n"
            "[TimingPoints]\n"
            "804,463.720463320463\n"
            "5000,-100\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
        )
        beatmap = parse_osu(text)
        red, green = beatmap.timing_points
        self.assertTrue(red.uninherited)
        self.assertEqual(red.meter, 4)
        self.assertAlmostEqual(red.bpm, 60000.0 / 463.720463320463)
        self.assertFalse(green.uninherited)
        self.assertAlmostEqual(green.sv, 1.0)

    def test_legacy_short_timing_line_without_beat_length_raises(self):
        text = "osu file format v3\n[TimingPoints]\n804\n[HitObjects]\n64,64,1000,1,0\n"
        with self.assertRaises(OsuParseError):
            parse_osu(text)

    def test_negative_bpm_red_timing_point_accepted(self):
        text = (
            "osu file format v14\n"
            "[TimingPoints]\n"
            "19,-65.86169045,4,3,19,80,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
        )
        beatmap = parse_osu(text)
        point = beatmap.timing_points[0]
        self.assertTrue(point.uninherited)
        self.assertAlmostEqual(point.bpm, 60000.0 / -65.86169045)

    def test_nan_timing_point_is_degenerate_and_falls_back(self):
        text = (
            "osu file format v14\n"
            "[TimingPoints]\n"
            "1000,NaN,4,2,1,60,1,0\n"
            "[HitObjects]\n"
            "64,64,1000,1,0\n"
        )
        beatmap = parse_osu(text)
        self.assertTrue(beatmap.timing_points[0].degenerate)
        self.assertEqual(effective_timing(beatmap.timing_points, 1000.0)[:2], (120.0, 1.0))

    def test_nan_slider_pixel_length_is_unknown(self):
        text = (
            "osu file format v14\n"
            "[HitObjects]\n"
            "256,192,1000,2,0,B|320:192,1,NaN\n"
        )
        beatmap = parse_osu(text)
        self.assertEqual(len(beatmap.hit_objects), 1)
        self.assertEqual(beatmap.hit_objects[0].object_type, "slider")
        self.assertIsNone(beatmap.hit_objects[0].slider_pixel_length)

    def test_utf16_file_parses(self):
        import tempfile
        from pathlib import Path

        text = "osu file format v10\n[HitObjects]\n64,64,1000,1,0\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "utf16.osu"
            path.write_bytes(text.encode("utf-16"))
            beatmap = parse_osu_file(path)
            self.assertEqual(beatmap.format_version, 10)
            self.assertEqual(len(beatmap.hit_objects), 1)

    def test_slider_with_single_letter_curve_and_no_points(self):
        text = "osu file format v14\n[HitObjects]\n64,64,1000,2,0,I,1,100\n"
        beatmap = parse_osu(text)
        slider = beatmap.hit_objects[0]
        self.assertEqual(slider.slider_curve_type, "I")
        self.assertEqual(slider.slider_points, ())

    def test_slider_points_skip_non_coordinate_tokens(self):
        text = "osu file format v14\n[HitObjects]\n64,64,1000,2,0,D|I|C|K|S|B|82:226|83:229,1,100\n"
        beatmap = parse_osu(text)
        slider = beatmap.hit_objects[0]
        self.assertEqual(slider.slider_curve_type, "D")
        self.assertEqual(slider.slider_points, ((82.0, 226.0), (83.0, 229.0)))


if __name__ == "__main__":
    unittest.main()
