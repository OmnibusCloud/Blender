from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge" / "bridge_scene_attachments.py"


class BridgeSceneAttachmentTests(unittest.TestCase):
    def test_summarize_scene_attachment_metadata_groups_packed_and_uploaded_counts(self) -> None:
        module = self._load_module(self._create_fake_bpy())

        summary = module.summarize_scene_attachment_metadata(
            [
                {"Kind": "ImageAsset", "PackagingStrategy": "PackedBlendCopy"},
                {"Kind": "ImageAsset", "PackagingStrategy": "PackedBlendCopy"},
                {"Kind": "Font", "PackagingStrategy": "SceneAttachmentBlob"},
                {"Kind": "Sound", "PackagingStrategy": "SceneAttachmentBlob"},
            ]
        )

        self.assertEqual(4, summary["TotalCount"])
        self.assertEqual(2, summary["PackedCount"])
        self.assertEqual(2, summary["AttachmentCount"])
        self.assertIn("Image assets × 2", summary["PackedSummary"])
        self.assertIn("Fonts × 1", summary["AttachmentSummary"])
        self.assertIn("Sounds × 1", summary["AttachmentSummary"])
        self.assertIn("Image assets × 2", summary["CountSummary"])

    def test_collect_scene_attachment_metadata_collects_cache_file_as_scene_attachment_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_path = pathlib.Path(temp_directory) / "simulation_cache.abc"
            cache_path.write_text("cache")
            fake_bpy = self._create_fake_bpy(cache_files=[types.SimpleNamespace(filepath=str(cache_path))])

            module = self._load_module(fake_bpy)
            attachments = module.collect_scene_attachment_metadata()

            self.assertEqual(1, len(attachments))
            self.assertEqual("CacheFile", attachments[0]["Kind"])
            self.assertEqual("SceneAttachmentBlob", attachments[0]["PackagingStrategy"])
            self.assertEqual(f"deps/cache-files/{cache_path.name}", attachments[0]["RelativePath"])
            self.assertEqual(str(cache_path), attachments[0]["OriginalPath"])

    def test_collect_scene_attachment_metadata_collects_sound_and_movie_clip_as_scene_attachment_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            sound_path = pathlib.Path(temp_directory) / "sound.wav"
            sound_path.write_text("sound")
            clip_path = pathlib.Path(temp_directory) / "clip.mp4"
            clip_path.write_text("clip")
            fake_bpy = self._create_fake_bpy(
                sounds=[types.SimpleNamespace(filepath=str(sound_path))],
                movieclips=[types.SimpleNamespace(filepath=str(clip_path))],
            )

            module = self._load_module(fake_bpy)
            attachments = module.collect_scene_attachment_metadata()

            self.assertEqual(2, len(attachments))
            self.assertEqual("Sound", attachments[0]["Kind"])
            self.assertEqual(f"deps/sounds/{sound_path.name}", attachments[0]["RelativePath"])
            self.assertEqual("MovieClip", attachments[1]["Kind"])
            self.assertEqual(f"deps/movie-clips/{clip_path.name}", attachments[1]["RelativePath"])

    def test_collect_scene_attachment_metadata_collects_image_sequence_as_scene_attachment_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            sequence_directory = pathlib.Path(temp_directory) / "sequence"
            sequence_directory.mkdir()
            frame_1 = sequence_directory / "plate_0001.png"
            frame_2 = sequence_directory / "plate_0002.png"
            frame_1.write_text("frame-1")
            frame_2.write_text("frame-2")
            fake_bpy = self._create_fake_bpy(
                images=[types.SimpleNamespace(filepath=str(frame_1), source="SEQUENCE", packed_file=None, name="Plate")]
            )

            module = self._load_module(fake_bpy)
            attachments = module.collect_scene_attachment_metadata()

            self.assertEqual(2, len(attachments))
            self.assertEqual("ImageSequenceFrame", attachments[0]["Kind"])
            self.assertEqual("SceneAttachmentBlob", attachments[0]["PackagingStrategy"])
            self.assertEqual(f"deps/image-sequences/Plate/{frame_1.name}", attachments[0]["RelativePath"])
            self.assertEqual(str(frame_1), attachments[0]["OriginalPath"])
            self.assertEqual("ImageSequenceFrame", attachments[1]["Kind"])
            self.assertEqual(f"deps/image-sequences/Plate/{frame_2.name}", attachments[1]["RelativePath"])

    def test_collect_scene_attachment_metadata_collects_linked_library_and_volume_as_scene_attachment_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library_path = pathlib.Path(temp_directory) / "library.blend"
            library_path.write_text("library")
            volume_path = pathlib.Path(temp_directory) / "volume.vdb"
            volume_path.write_text("volume")
            fake_bpy = self._create_fake_bpy(
                libraries=[types.SimpleNamespace(filepath=str(library_path), packed_file=None)],
                volumes=[types.SimpleNamespace(filepath=str(volume_path))],
            )

            module = self._load_module(fake_bpy)
            attachments = module.collect_scene_attachment_metadata()

            self.assertEqual(2, len(attachments))
            self.assertEqual("LinkedLibrary", attachments[0]["Kind"])
            self.assertEqual(f"deps/linked-libraries/{library_path.name}", attachments[0]["RelativePath"])
            self.assertEqual("Volume", attachments[1]["Kind"])
            self.assertEqual(f"deps/volumes/{volume_path.name}", attachments[1]["RelativePath"])

    def test_collect_scene_attachment_metadata_collects_vse_media_as_scene_attachment_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            image_directory = pathlib.Path(temp_directory) / "image-strip"
            image_directory.mkdir()
            image_path = image_directory / "frame_0001.png"
            image_path.write_text("image")
            movie_path = pathlib.Path(temp_directory) / "strip.mp4"
            movie_path.write_text("movie")
            sound_path = pathlib.Path(temp_directory) / "strip.wav"
            sound_path.write_text("sound")

            fake_strip_editor = types.SimpleNamespace(
                strips_all=[
                    types.SimpleNamespace(
                        type="IMAGE",
                        name="Image Strip",
                        directory=str(image_directory),
                        elements=[types.SimpleNamespace(filename=image_path.name)],
                    ),
                    types.SimpleNamespace(type="MOVIE", name="Movie Strip", filepath=str(movie_path)),
                    types.SimpleNamespace(type="SOUND", name="Sound Strip", filepath=str(sound_path), sound=types.SimpleNamespace(filepath=str(sound_path))),
                ]
            )
            fake_bpy = self._create_fake_bpy(scenes=[types.SimpleNamespace(sequence_editor=fake_strip_editor)])

            module = self._load_module(fake_bpy)
            attachments = module.collect_scene_attachment_metadata()

            self.assertEqual(3, len(attachments))
            self.assertEqual("VseImageStripFrame", attachments[0]["Kind"])
            self.assertEqual(f"deps/vse/image-strips/Image_Strip/{image_path.name}", attachments[0]["RelativePath"])
            self.assertEqual("VseMovieStrip", attachments[1]["Kind"])
            self.assertEqual("VseSoundStrip", attachments[2]["Kind"])

    @staticmethod
    def _create_fake_bpy(*, images: list[object] | None = None, fonts: list[object] | None = None, cache_files: list[object] | None = None, libraries: list[object] | None = None, volumes: list[object] | None = None, sounds: list[object] | None = None, movieclips: list[object] | None = None, scenes: list[object] | None = None):
        return types.SimpleNamespace(
            data=types.SimpleNamespace(
                images=images or [],
                fonts=fonts or [],
                cache_files=cache_files or [],
                libraries=libraries or [],
                volumes=volumes or [],
                sounds=sounds or [],
                movieclips=movieclips or [],
                scenes=scenes or [],
            ),
            path=types.SimpleNamespace(abspath=lambda value: value),
        )

    def _load_module(self, fake_bpy):
        spec = importlib.util.spec_from_file_location("bridge_scene_attachments", MODULE_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load bridge scene attachments module from {MODULE_PATH}")

        previous_bpy = sys.modules.get("bpy")
        sys.modules["bpy"] = fake_bpy
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if previous_bpy is None:
                sys.modules.pop("bpy", None)
            else:
                sys.modules["bpy"] = previous_bpy


if __name__ == "__main__":
    unittest.main()
