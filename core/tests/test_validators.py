import io
import unittest

from PIL import Image

from core import validators
from core.exceptions import ApiError

NAMES = ["Кино", "Музыка"]


def fields_of(fn, *a):
    try:
        fn(*a)
    except ApiError as exc:
        return exc.fields
    return {}


def base(**over):
    d = {"email": "a@example.com", "password": "secret123", "name": "Аня", "age": "25",
         "gender": "female", "looking_for": "male", "bio": "", "interests": []}
    d.update(over)
    return d


class TestValidators(unittest.TestCase):
    def test_valid_registration(self):
        data = validators.validate_registration(base(email=" A@Example.COM ", interests=["кино"]), NAMES)
        self.assertEqual(data["email"], "a@example.com")
        self.assertEqual(data["interests"], ["Кино"])
        self.assertEqual(data["age"], 25)

    def test_each_bad_field_reports_own_error(self):
        cases = {
            "email": ["", "nope", "a@b", "a b@c.com"],
            "password": ["", "short1", "onlyletters", "12345678"],
            "name": ["", "A", "<script>", "x" * 51],
            "age": ["", "abc", "17", "100", "-5"],
            "gender": ["", "robot"],
            "looking_for": ["", "all"],
            "bio": ["x" * 501],
        }
        for field, values in cases.items():
            for v in values:
                f = fields_of(validators.validate_registration, base(**{field: v}), NAMES)
                self.assertIn(field, f, f"{field}={v!r} должно быть отвергнуто")

    def test_interests_rules(self):
        self.assertIn("interests", fields_of(validators.validate_registration, base(interests=["Чужое"]), NAMES))
        many = [f"I{i}" for i in range(9)]
        self.assertIn("interests", fields_of(validators.validate_registration, base(interests=many), many))

    def test_all_errors_returned_at_once(self):
        f = fields_of(validators.validate_registration, base(email="x", age="5", name=""), NAMES)
        self.assertEqual({"email", "age", "name"}, set(f))

    def test_message_and_interest_name(self):
        self.assertEqual(validators.clean_message("  hi "), "hi")
        with self.assertRaises(validators._Bad):
            validators.clean_interest_name("<b>")


class TestPhoto(unittest.TestCase):
    def img(self, fmt, size=(1200, 800)):
        buf = io.BytesIO()
        Image.new("RGB", size, (10, 120, 200)).save(buf, fmt)
        return buf.getvalue()

    def test_accepts_formats_and_normalises(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            out = Image.open(io.BytesIO(validators.process_photo(self.img(fmt))))
            self.assertEqual((out.format, out.size), ("JPEG", (600, 750)))

    def test_rejects_non_images_and_other_formats(self):
        for raw in (b"", b"not an image", b"<svg xmlns='http://www.w3.org/2000/svg'/>", self.img("GIF")):
            self.assertIn("photo", fields_of(validators.process_photo, raw))

    def test_rejects_huge_file(self):
        self.assertIn("photo", fields_of(validators.process_photo, b"0" * (5 * 1024 * 1024 + 1)))


if __name__ == "__main__":
    unittest.main()
