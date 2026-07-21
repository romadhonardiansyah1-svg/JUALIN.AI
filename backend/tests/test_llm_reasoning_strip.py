"""Regression: reasoning (<think>) must never leak to the buyer-facing chat,
for both non-streaming and streaming paths, regardless of model."""
import asyncio
import unittest

from services.llm_router import strip_think, _strip_think_stream


async def _collect(chunks):
    async def _gen():
        for c in chunks:
            yield c

    out = []
    async for token in _strip_think_stream(_gen()):
        out.append(token)
    return "".join(out)


class ReasoningStripTests(unittest.TestCase):
    def test_non_stream_removes_think_block(self):
        text = "<think>alasan internal</think>Halo Kak, ada yang bisa dibantu?"
        self.assertEqual(strip_think(text), "Halo Kak, ada yang bisa dibantu?")

    def test_non_stream_multiline_and_thinking_variant(self):
        text = "<thinking>\nstep 1\nstep 2\n</thinking>Jawaban akhir."
        self.assertEqual(strip_think(text), "Jawaban akhir.")

    def test_non_stream_keeps_plain_text(self):
        text = "Produk A harga 10rb, stok ada."
        self.assertEqual(strip_think(text), "Produk A harga 10rb, stok ada.")

    def test_stream_removes_think_when_split_across_chunks(self):
        chunks = ["<th", "ink>ala", "san</thi", "nk>Ja", "waban Kak"]
        self.assertEqual(asyncio.run(_collect(chunks)), "Jawaban Kak")

    def test_stream_plain_text_passes_through(self):
        chunks = ["Ha", "lo ", "Kak"]
        self.assertEqual(asyncio.run(_collect(chunks)), "Halo Kak")

    def test_stream_does_not_leak_open_angle_that_is_not_think(self):
        chunks = ["harga < ", "20rb"]
        self.assertEqual(asyncio.run(_collect(chunks)), "harga < 20rb")

    def test_stream_unclosed_think_is_fully_suppressed(self):
        chunks = ["<think>masih berpikir tanpa penutup"]
        self.assertEqual(asyncio.run(_collect(chunks)), "")


if __name__ == "__main__":
    unittest.main()
