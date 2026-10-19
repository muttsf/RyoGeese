# RyoGeese 许可范围

RyoGeese licensing scope

Copyright (C) 2026 手电加鞭

The original project-owned desktop, build-tool and GPU reader source is released
under GNU GPL version 3 only (GPL-3.0-only). See LICENSE / LICENSE.txt.
The author's project logo is distributed with the project under the same policy.

The original reader source in native/ and its identical CUDA source shipped at
app/reader/gpu/dash.cu additionally has the permission in native/ADDITIONAL_PERMISSION.txt.
The installed copy is notices/RyoGeese_Reader_Additional_Permission.txt.
This permission is scoped to that owned reader. It does NOT apply to the desktop
SimulationCraft-derived priority evaluation, data, or any third-party source.
Existing accepted C#/CUDA source bytes are kept unchanged; directory-level
licensing statements cover them without altering the CUDA source hash stamp.

SimulationCraft-derived code and data, including app/foundation/simc_runtime/,
retain the upstream GPLv3 licence and attribution. No linking exception is added
to SimulationCraft or its derived parts. The pinned upstream commit is
3dcabb94dd32f786786c67541dfd10db9f39e43b. The adaptation and product simplifications
are described in THIRD_PARTY_NOTICES.txt. The upstream licence is in
notices/SimulationCraft_LICENSE.txt.

Third-party components are not relicensed as project-owned GPL source:
- runtime/python/ and bundled Tcl/Tk: original PSF/Tcl/Tk and third-party terms;
- runtime/dotnet/: Microsoft .NET Library Windows binary and third-party terms;
- runtime/gpu/: original NVIDIA terms, including CUDA and current cuDNN redist terms;
- reader/bin/ third-party DLLs: original NuGet / Microsoft SDK terms;
- reader/upstream/ch_PP-OCRv4_rec_mobile.onnx: original RapidOCR/PaddleOCR Apache-2.0 terms.
Component-to-notice mapping: notices/NOTICE_INDEX.txt, NUMBERED_NOTICE_INDEX.json
and PACKAGE_INDEX.json. Original notices and metadata are preserved.

Only the independent game addon is in the RyoGeese-Dash repository. Its owned
source is GPL-3.0-only without this reader permission. Neither project's licence
grants rights in the game client, internet audio or game skill artwork.

Corresponding Source: publish the complete source tree at the exact release tag
alongside the installer. See SOURCE.txt. Do not substitute an unversioned main
branch for the exact release source or omit the reader/build scripts/model pins.
