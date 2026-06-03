from __future__ import annotations

import os
import re

import bpy

PACKAGING_STRATEGY_PACKED_BLEND_COPY = "PackedBlendCopy"
PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB = "SceneAttachmentBlob"

KIND_DISPLAY_NAMES = {
    "CacheFile": "Cache files",
    "Font": "Fonts",
    "ImageAsset": "Image assets",
    "ImageSequenceFrame": "Image sequences",
    "LinkedLibrary": "Linked libraries",
    "MovieClip": "Movie clips",
    "Sound": "Sounds",
    "Volume": "Volume files",
    "VseImageStripFrame": "VSE image-strip frames",
    "VseMovieStrip": "VSE movie strips",
    "VseSoundStrip": "VSE sound strips",
}


def _safe_relative_component(value: str) -> str:
    sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    sanitized = sanitized.strip("._")
    return sanitized or "item"


def _display_kind_name(kind: str) -> str:
    return KIND_DISPLAY_NAMES.get(kind, kind)


def _collect_image_sequence_frame_paths(sequence_path: str) -> list[str]:
    directory = os.path.dirname(sequence_path)
    file_name = os.path.basename(sequence_path)
    if not directory or not os.path.isdir(directory) or not file_name:
        return []

    match = re.match(r"^(.*?)(\d+)(\.[^.]+)$", file_name)
    if match is None:
        return []

    prefix, digits, extension = match.groups()
    pattern = re.compile(rf"^{re.escape(prefix)}(\d{{{len(digits)}}}){re.escape(extension)}$", re.IGNORECASE)
    matches: list[tuple[int, str]] = []
    for candidate_name in os.listdir(directory):
        candidate_match = pattern.match(candidate_name)
        if candidate_match is None:
            continue

        candidate_path = os.path.join(directory, candidate_name)
        if not os.path.isfile(candidate_path):
            continue

        matches.append((int(candidate_match.group(1)), candidate_path))

    return [path for _, path in sorted(matches, key=lambda item: item[0])]


def _count_by_kind(attachments: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attachment in attachments:
        kind = str(attachment.get("Kind") or "Unknown")
        counts[kind] = counts.get(kind, 0) + 1

    return counts


def _count_summary(attachments: list[dict[str, object]]) -> str:
    counts = _count_by_kind(attachments)
    if not counts:
        return ""

    return " | ".join(
        f"{_display_kind_name(kind)} × {count}"
        for kind, count in sorted(counts.items(), key=lambda item: _display_kind_name(item[0]).lower())
    )


def summarize_scene_attachment_metadata(attachments: list[dict[str, object]]) -> dict[str, object]:
    packed_attachments = [me for me in attachments if str(me.get("PackagingStrategy") or "") == PACKAGING_STRATEGY_PACKED_BLEND_COPY]
    uploaded_attachments = [me for me in attachments if str(me.get("PackagingStrategy") or "") == PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB]

    return {
        "TotalCount": len(attachments),
        "CountSummary": _count_summary(attachments),
        "PackedCount": len(packed_attachments),
        "PackedSummary": _count_summary(packed_attachments),
        "AttachmentCount": len(uploaded_attachments),
        "AttachmentSummary": _count_summary(uploaded_attachments),
    }


def collect_scene_attachment_metadata() -> list[dict[str, object]]:
    attachments: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for image in getattr(bpy.data, "images", []):
        if getattr(image, "packed_file", None) is not None:
            continue

        source = str(getattr(image, "source", "") or "")
        if source not in {"FILE", "SEQUENCE"}:
            continue

        image_path = bpy.path.abspath(str(getattr(image, "filepath", "") or ""))
        if not image_path or not os.path.exists(image_path):
            continue

        if source == "SEQUENCE":
            sequence_name = _safe_relative_component(str(getattr(image, "name", "") or os.path.splitext(os.path.basename(image_path))[0]))
            frame_paths = _collect_image_sequence_frame_paths(image_path)
            if not frame_paths:
                continue

            for frame_path in frame_paths:
                key = ("ImageSequenceFrame", frame_path)
                if key in seen:
                    continue

                seen.add(key)
                attachments.append(
                    {
                        "Kind": "ImageSequenceFrame",
                        "BlobId": "",
                        "OriginalPath": frame_path,
                        "RelativePath": f"deps/image-sequences/{sequence_name}/{os.path.basename(frame_path)}",
                        "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
                    }
                )

            continue

        key = ("ImageAsset", image_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "ImageAsset",
                "BlobId": "",
                "OriginalPath": image_path,
                "RelativePath": f"deps/images/{os.path.basename(image_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_PACKED_BLEND_COPY,
            }
        )

    for font in getattr(bpy.data, "fonts", []):
        font_path = str(getattr(font, "filepath", "") or "")
        if not font_path or font_path == "<builtin>":
            continue

        resolved_font_path = bpy.path.abspath(font_path)
        if not resolved_font_path or not os.path.exists(resolved_font_path):
            continue

        key = ("Font", resolved_font_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "Font",
                "BlobId": "",
                "OriginalPath": resolved_font_path,
                "RelativePath": f"deps/fonts/{os.path.basename(resolved_font_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
            }
        )

    for cache_file in getattr(bpy.data, "cache_files", []):
        cache_path = str(getattr(cache_file, "filepath", "") or "")
        if not cache_path:
            continue

        resolved_cache_path = bpy.path.abspath(cache_path)
        if not resolved_cache_path or not os.path.exists(resolved_cache_path):
            continue

        key = ("CacheFile", resolved_cache_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "CacheFile",
                "BlobId": "",
                "OriginalPath": resolved_cache_path,
                "RelativePath": f"deps/cache-files/{os.path.basename(resolved_cache_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
            }
        )

    for library in getattr(bpy.data, "libraries", []):
        library_path = str(getattr(library, "filepath", "") or "")
        if not library_path:
            continue

        if getattr(library, "packed_file", None) is not None:
            continue

        resolved_library_path = bpy.path.abspath(library_path)
        if not resolved_library_path or not os.path.exists(resolved_library_path):
            continue

        key = ("LinkedLibrary", resolved_library_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "LinkedLibrary",
                "BlobId": "",
                "OriginalPath": resolved_library_path,
                "RelativePath": f"deps/linked-libraries/{os.path.basename(resolved_library_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
            }
        )

    for volume in getattr(bpy.data, "volumes", []):
        volume_path = str(getattr(volume, "filepath", "") or "")
        if not volume_path:
            continue

        resolved_volume_path = bpy.path.abspath(volume_path)
        if not resolved_volume_path or not os.path.exists(resolved_volume_path):
            continue

        key = ("Volume", resolved_volume_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "Volume",
                "BlobId": "",
                "OriginalPath": resolved_volume_path,
                "RelativePath": f"deps/volumes/{os.path.basename(resolved_volume_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
            }
        )

    for sound in getattr(bpy.data, "sounds", []):
        sound_path = str(getattr(sound, "filepath", "") or "")
        if not sound_path:
            continue

        resolved_sound_path = bpy.path.abspath(sound_path)
        if not resolved_sound_path or not os.path.exists(resolved_sound_path):
            continue

        key = ("Sound", resolved_sound_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "Sound",
                "BlobId": "",
                "OriginalPath": resolved_sound_path,
                "RelativePath": f"deps/sounds/{os.path.basename(resolved_sound_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
            }
        )

    for movie_clip in getattr(bpy.data, "movieclips", []):
        clip_path = str(getattr(movie_clip, "filepath", "") or "")
        if not clip_path:
            continue

        resolved_clip_path = bpy.path.abspath(clip_path)
        if not resolved_clip_path or not os.path.exists(resolved_clip_path):
            continue

        key = ("MovieClip", resolved_clip_path)
        if key in seen:
            continue

        seen.add(key)
        attachments.append(
            {
                "Kind": "MovieClip",
                "BlobId": "",
                "OriginalPath": resolved_clip_path,
                "RelativePath": f"deps/movie-clips/{os.path.basename(resolved_clip_path)}",
                "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
            }
        )

    for scene in getattr(bpy.data, "scenes", []):
        editor = getattr(scene, "sequence_editor", None)
        if editor is None:
            continue

        for strip in getattr(editor, "strips_all", []):
            strip_type = str(getattr(strip, "type", "") or "")
            strip_name = _safe_relative_component(str(getattr(strip, "name", "") or strip_type or "Unnamed"))

            if strip_type == "IMAGE":
                directory = bpy.path.abspath(str(getattr(strip, "directory", "") or ""))
                elements = list(getattr(strip, "elements", []))
                if not directory or not os.path.isdir(directory) or not elements:
                    continue

                for element in elements:
                    filename = str(getattr(element, "filename", "") or "")
                    if not filename:
                        continue

                    resolved_strip_path = os.path.join(directory, filename)
                    if not os.path.exists(resolved_strip_path):
                        continue

                    key = ("VseImageStripFrame", resolved_strip_path)
                    if key in seen:
                        continue

                    seen.add(key)
                    attachments.append(
                        {
                            "Kind": "VseImageStripFrame",
                            "BlobId": "",
                            "OriginalPath": resolved_strip_path,
                            "RelativePath": f"deps/vse/image-strips/{strip_name}/{os.path.basename(resolved_strip_path)}",
                            "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
                        }
                    )

            elif strip_type == "MOVIE":
                movie_path = bpy.path.abspath(str(getattr(strip, "filepath", "") or ""))
                if not movie_path or not os.path.exists(movie_path):
                    continue

                key = ("VseMovieStrip", movie_path)
                if key in seen:
                    continue

                seen.add(key)
                attachments.append(
                    {
                        "Kind": "VseMovieStrip",
                        "BlobId": "",
                        "OriginalPath": movie_path,
                        "RelativePath": f"deps/vse/movie-strips/{strip_name}/{os.path.basename(movie_path)}",
                        "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
                    }
                )

            elif strip_type == "SOUND":
                sound = getattr(strip, "sound", None)
                sound_path = bpy.path.abspath(str(getattr(sound, "filepath", "") or getattr(strip, "filepath", "") or ""))
                if not sound_path or not os.path.exists(sound_path):
                    continue

                key = ("VseSoundStrip", sound_path)
                if key in seen:
                    continue

                seen.add(key)
                attachments.append(
                    {
                        "Kind": "VseSoundStrip",
                        "BlobId": "",
                        "OriginalPath": sound_path,
                        "RelativePath": f"deps/vse/sound-strips/{strip_name}/{os.path.basename(sound_path)}",
                        "PackagingStrategy": PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
                    }
                )

    return attachments
