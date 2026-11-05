"""실행: 프로젝트 폴더에서  python -m unittest tests.test_dpapi_store -v"""
import os
import tempfile
import unittest

from core.dpapi_store import SessionStore, protect, unprotect


class TestDpapi(unittest.TestCase):
    def test_roundtrip(self):
        data = "비밀번호 P@ss!".encode("utf-8")
        enc = protect(data)
        self.assertNotIn(data, enc)
        self.assertEqual(unprotect(enc), data)

    def test_tampered_fails(self):
        enc = bytearray(protect(b"secret"))
        enc[-5] ^= 0xFF
        with self.assertRaises(OSError):
            unprotect(bytes(enc))


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "sessions.bin")

    def test_save_load(self):
        st = SessionStore(self.path)
        st.upsert({"name": "금강 관제서버", "host": "10.0.0.5", "rdp_user": "admin",
                   "rdp_password": "pw1", "protocol": "ftp", "ft_port": 21})
        st.save()
        with open(self.path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"10.0.0.5", raw)
        self.assertNotIn(b"pw1", raw)

        st2 = SessionStore(self.path)
        s = st2.get("금강 관제서버")
        self.assertEqual(s["rdp_password"], "pw1")
        self.assertEqual(s["rdp_port"], 3389)  # 기본값 채움

    def test_upsert_and_remove(self):
        st = SessionStore(self.path)
        st.upsert({"name": "A", "host": "1.1.1.1"})
        st.upsert({"name": "A", "host": "2.2.2.2"})
        self.assertEqual(len(st.sessions), 1)
        self.assertEqual(st.get("A")["host"], "2.2.2.2")
        self.assertTrue(st.remove("A"))
        self.assertFalse(st.remove("A"))

    def test_validation(self):
        st = SessionStore(self.path)
        with self.assertRaises(ValueError):
            st.upsert({"name": "", "host": "x"})
        with self.assertRaises(ValueError):
            st.upsert({"name": "x", "host": "y", "protocol": "scp"})


if __name__ == "__main__":
    unittest.main()
