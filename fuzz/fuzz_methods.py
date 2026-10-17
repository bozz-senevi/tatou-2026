import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server", "src"))

# import YOUR code — the registry of all methods + the declared error types
from watermarking_utils import METHODS, apply_watermark, read_watermark
from watermarking_method import WatermarkingError, SecretNotFoundError, InvalidKeyError

# A tiny valid PDF to use as the starting point for mutation
SEED = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n")

def mutate(data, rng):
    b = bytearray(data)
    for _ in range(rng.randint(1, 20)):      # make a handful of random edits
        i = rng.randrange(len(b))
        b[i] = rng.randrange(256)            # flip one byte to a random value
    return bytes(b)

# the oracle: these are the ONLY exceptions the interface allows
OK_ADD  = (ValueError, WatermarkingError)
OK_READ = (ValueError, WatermarkingError, SecretNotFoundError, InvalidKeyError)

rng = random.Random(1337)                    # fixed seed = reproducible run
for i in range(1000):
    name = rng.choice(list(METHODS))         # pick a random method
    pdf  = mutate(SEED, rng)                  # a random broken PDF
    try:
        apply_watermark(method=name, pdf=pdf, secret="test", key="key123")
    except OK_ADD:
        pass                                 # expected — not a bug
    except Exception as e:                    # anything else = finding
        print(f"[CRASH] {name} add_watermark -> {type(e).__name__}: {e}")
    try:
        s = "a\x00b\x01c"
        wm = apply_watermark(method=name, pdf=SEED, secret=s, key="key123")
        back = read_watermark(method=name, pdf=wm, key="key123")
        if back != s:
            print(f"[ROUNDTRIP] {name}: wrote {s!r} but read {back!r}")
    except (ValueError, WatermarkingError, SecretNotFoundError, InvalidKeyError):
        pass
