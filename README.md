<div align="center">
  <h1>Fusion Slicer Exporter</h1>
  <a href="https://github.com/TUNA-THE-FIRST/FusionSlicerExporter/actions/workflows/tests.yml"><img src="https://github.com/TUNA-THE-FIRST/FusionSlicerExporter/actions/workflows/tests.yml/badge.svg" alt="Tests"/></a>
  <a href="https://github.com/TUNA-THE-FIRST/FusionSlicerExporter/releases/latest"><img src="https://img.shields.io/github/v/release/TUNA-THE-FIRST/FusionSlicerExporter" alt="Latest release"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License: MIT"/></a>

[Installation](#installation-and-setup)⚙️ | [Usage](#usage)🏃 | [Sending Colors](#sending-colors)🎨 | [Slicer Locations](#change_slicer_stl)🔁 | [Folder Structure](#folder-structure-of-the-repository)📂 | [Development](#development)🧪 | [Contact](#contact)📫 | [Credits](#credits)📖
</div>

### Introduction <a name="introduction"></a>

**Fusion Slicer Exporter** is an Autodesk Fusion add-in that sends selected bodies or components, including the colors you applied in Fusion, to **Snapmaker Orca, Bambu Studio, OrcaSlicer or PrusaSlicer** with a single click. It runs on Windows and macOS.

It started as a fork of [ClickNSend](https://github.com/bankh/Fusion360_ClickNSend) by Sinan Bank (see [Credits](#credits)).

#### Motivation

The standard print utility in Fusion 360 (as of version 2.0.21538) lacks efficient functionality for exporting multiple selected bodies or components directly to third-party slicers like Orca Slicer for downstream 3D printing operations. This limitation creates friction in the design-to-print workflow, especially when working with complex multi-body designs.

#### Benefits

- **Simplified Workflow**: Send any selection of bodies or components directly to your slicer with a single click
- **Time-Saving**: Eliminate the need for manual STL export and import processes
- **Seamless Integration**: Adds a convenient 3D printer icon to your Fusion 360 Insert panel
- **Multiple Slicers**: Pick Snapmaker Orca, Bambu Studio, OrcaSlicer or PrusaSlicer in the dialog, so each printer can use its own slicer
- **Colors Included**: Colors applied with Fusion's Appearance tool arrive painted in the slicer
- **Multi-Selection Support**: Export single or multiple geometries simultaneously

Once installed, Fusion Slicer Exporter integrates directly into your Fusion 360 interface, providing an intuitive one-click solution for sending your designs to your favorite slicer software.

### Folder Structure of the Repository <a name="folder-structure-of-the-repository"></a>

<details>
<summary>Click to expand Folder Structure of the Repository</summary>

```FusionSlicerExporter/
├── .github/workflows/      # Tests on Windows/macOS/Linux; release zips built from tagged source
├── commands/               # Command implementations
│   ├── commandDialog/      # UI dialog components and the color (OBJ/MTL) exporter
│   └── __init__.py         # Commands initialization
├── lib/                    # Library files
│   └── fusionAddInUtils/   # Fusion 360 Add-In utilities
├── AddInIcon.svg           # Add-In icon for Fusion 360
├── FusionSlicerExporter.manifest  # Add-In manifest file (name must match the folder)
├── FusionSlicerExporter.py        # Main Add-In entry point (name must match the folder)
├── LICENSE                 # MIT License file
├── README.md               # This file
├── config.py               # Configuration settings / settings loader
├── slicers.py              # Supported slicers and where to find them
├── tests/                  # Offline tests, plus Fusion scripts to test/diagnose the color export
├── tools/                  # make_icons.py (toolbar icons), make_release.py (release zips)
└── settings.json           # Optional slicer locations (empty = find automatically)
```

</details>

### Installation and Setup <a name="installation-and-setup"></a>

<details>
<summary>Click to expand Installation and Setup</summary>

Works with Autodesk Fusion on **Windows and macOS**, together with any of these slicers: [Snapmaker Orca](https://github.com/Snapmaker/OrcaSlicer/releases), [Bambu Studio](https://bambulab.com/en/download/studio), [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer/releases) and [PrusaSlicer](https://www.prusa3d.com/page/prusaslicer_424/).

**Option A, download:** get `FusionSlicerExporter-v<version>-Windows.zip` or `-macOS.zip` from the [latest release](https://github.com/TUNA-THE-FIRST/FusionSlicerExporter/releases/latest). GitHub builds these zips from the tagged source in this repository (see `.github/workflows/release.yml`), and each contains a short `INSTALL.txt`.

**Option B, git clone** (update later with `git pull`):

- **Windows** (Command Prompt): `cd /d "%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns"` then `git clone https://github.com/TUNA-THE-FIRST/FusionSlicerExporter.git`
- **macOS** (Terminal): `cd ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns` then `git clone https://github.com/TUNA-THE-FIRST/FusionSlicerExporter.git`

Then skip to step 3.

1. Extract the zip. Inside is a folder named `FusionSlicerExporter`. Keep that name: it has to match the `FusionSlicerExporter.py` and `FusionSlicerExporter.manifest` files inside it, or Fusion won't load the add-in.

2. Move the `FusionSlicerExporter` folder into Fusion's Add-Ins folder:
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns` (paste this into File Explorer's address bar).
   - **macOS:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns` (in Finder, choose Go → Go to Folder…).

   You can also find the folder from Fusion: `Utilities` → `Scripts and Add-Ins` (or `Shift+S`), `Add-Ins` tab, green ➕ icon.
![Fusion360_MWHySdwzPN](https://github.com/user-attachments/assets/d7297c58-c862-4caa-b3af-4c2d90b38292)
![Fusion360_MUjPGD653B](https://github.com/user-attachments/assets/547c0e1a-0e40-4353-8ca7-af8996bae7b0)
![Fusion360_SWeHkOoxGB](https://github.com/user-attachments/assets/15f50c07-d8e6-4534-aed1-7777bee9d516)

3. Restart Fusion. The add-in starts automatically. If it doesn't, open `Scripts and Add-Ins` (`Shift+S`), select `FusionSlicerExporter` on the `Add-Ins` tab and click `Run` (tick `Run on Startup` to keep it on).
![Fusion360_RxQlbhzfp4](https://github.com/user-attachments/assets/ffac7848-9f20-4f20-bb63-1d56bc5f5b57)

4. The **Send to Slicer** button appears in the `Solid` workspace's `Insert` panel. Choose the slicer at the top of its dialog; it remembers your last choice.
![Fusion360_cUFjQkscWg](https://github.com/user-attachments/assets/4beaa395-48d5-4e13-aea2-add79c525758)

The add-in finds the slicers on its own when they're installed in the usual place (on Windows it also finds custom install folders). Slicers it can't find are marked "(not found)" in the dialog; see [How to change the Slicer Path](#change_slicer_stl).

**Windows tip:** turn on the slicer's single-instance preference so each send goes into your open slicer window instead of opening a new one:

| Slicer | Preference |
|---|---|
| Snapmaker Orca | Allow only one Snapmaker Orca instance |
| Bambu Studio | Keep only one Bambu Studio instance |
| OrcaSlicer | Allow only one OrcaSlicer instance |
| PrusaSlicer | Allow just a single PrusaSlicer instance |

On macOS, sends already go into the open window, except colored models for Bambu Studio (see [Sending Colors](#sending-colors)).

</details>

### Usage <a name="usage"></a>

<details>
<summary>Click to expand Usage</summary>

1. With your models open in the active window of Fusion 360, select the bodies that you want to send to the slicer. (e.g., sample Cube and Rectangular Box below)
![Fusion360_K07RrYpt1P](https://github.com/user-attachments/assets/455bb081-7335-45b4-b099-2708c0dbbc24)

2. Click the **Send to Slicer** button (the printer icon in your Fusion 360 Insert panel), pick the slicer and click OK. Each selected body is sent separately to the slicer with its default settings (or as one colored object, see [Sending Colors](#sending-colors)).

Single Body:
![Fusion360_nUtPGZ4SRt](https://github.com/user-attachments/assets/03a7120d-08e9-4306-b0a7-48ccfe0c3b56)
![EQeUZfO25L](https://github.com/user-attachments/assets/0d38c83d-e902-4a51-86a2-5f25130f290a)

Multiple Bodies:
![Fusion360_beVK8jCO7B](https://github.com/user-attachments/assets/7a115d7e-2e1b-4131-947d-5d5f7048d1cb)
![ll8fckRHFy](https://github.com/user-attachments/assets/0c34e3db-9f8e-4789-885a-ea942264733e)

__Note:__  
**1-** The add-in does not include any 3D packing or size verification to check whether objects will fit on your 3D printer's build plate. It assumes you are familiar with your 3D printer's dimensions and capabilities. Since the code is open-source, you're welcome to modify it to add these features if needed.  
**2-** Once you send multiple bodies as separate objects, you need to adjust their positions and orientations inside the slicer. Currently, there is no effort to optimize it from my side. (Please see the end of the former note.)

</details>

### Sending Colors <a name="sending-colors"></a>

<details>
<summary>Click to expand Sending Colors</summary>

Colors you apply in Fusion with the **Appearance** tool (to bodies, faces or components) are sent along, so the slicer paints the model for you. Leave **Keep Fusion colors** checked in the dialog (it is on by default). When nothing in the selection has an applied appearance, the bodies are sent as plain STL files instead.

How each slicer receives the colors:

| Slicer | What happens |
|---|---|
| **Snapmaker Orca** | An **Obj file Import color** window maps each Fusion color to a filament: **Color match** picks your closest loaded filaments, **Keep color** / **Add** create filaments in the exact Fusion colors. **Then select the imported object and set its filament to 1** (works around a Snapmaker Orca 2.4 bug that prints faces mapped to filament 1 with another filament; always safe). |
| **OrcaSlicer** | The same **Obj file Import color** window (**Color match**, or pick a filament per color). No extra step: OrcaSlicer has fixed the filament-1 bug. |
| **Bambu Studio** | A **Standard 3mf Import color** window with the same mapping. The add-in sends Bambu Studio a 3MF because its newer OBJ importer smooths colors and can lose small faces. On macOS, if Bambu Studio is already open, the model opens in a new Bambu Studio window, unless you turn on Preferences → **Keep only one Bambu Studio instance** (then choose to import the geometry when it asks). |
| **PrusaSlicer** | PrusaSlicer has no color import window, so the add-in paints the colors onto extruders itself, the color covering the most surface on extruder 1, the next on 2, and so on (up to 16), and shows which color went where. Load matching filaments in those extruders; the painting is used by printer profiles with enough extruders or tools (e.g. MMU3 or XL). |

**Colored bodies: One object (keeps layout)** puts all selected bodies into one object, positioned exactly as in Fusion, with a single color window. **Separate objects** sends each colored body as its own object; with Snapmaker Orca and OrcaSlicer that means one color window per body. Bodies without applied colors are sent as STL either way.

In the Orca color windows the color count can only go down (to merge colors), never above the number of colors found. To change it, double-click the number and type the new value; usually it's easier to keep the count and pick a filament per color, since several colors can share a filament.

If the slicer finds fewer colors than you used, copy `tests/FusionSlicerExporterColorReport` into Fusion's Scripts folder and run it with the design open. It lists every appearance on the design and the color the add-in reads from it, without changing anything.

Painted colors are lost if the object is split in the slicer ("Split to objects/parts"), so choose **Separate objects** in Fusion instead if you want to arrange bodies individually.

</details>

### Presentation Video (original ClickNSend) <a name="presentation-video"></a>
<a href="https://youtu.be/7a8Z9qCItDY">
    <img src="https://github.com/user-attachments/assets/e75340d7-da48-4b0d-aec2-30e0bb146eec" alt="Presentation4">
</a>

### How to change the Slicer Path or Export Format <a name="change_slicer_stl"></a>

<details>
<summary>Click to expand changing the Slicer</summary> 

`settings.json` (in the add-in folder) has an entry per slicer. Empty means "find it automatically":

```json
{
  "slicers": {
    "Snapmaker Orca": "",
    "Bambu Studio": "",
    "OrcaSlicer": "",
    "PrusaSlicer": ""
  }
}
```

The add-in looks in `/Applications` and `~/Applications` on macOS (PrusaSlicer also in `/Applications/Original Prusa Drivers`), and on Windows in the folder recorded by each slicer's installer plus the default folders:

| Slicer | macOS app | Windows default |
|---|---|---|
| Snapmaker Orca | `Snapmaker Orca.app` | `C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe` |
| Bambu Studio | `BambuStudio.app` | `C:\Program Files\Bambu Studio\bambu-studio.exe` |
| OrcaSlicer | `OrcaSlicer.app` | `C:\Program Files\OrcaSlicer\orca-slicer.exe` |
| PrusaSlicer | `PrusaSlicer.app` | `C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe` |

To use a copy somewhere else (a portable Windows zip, a renamed app, a second version), put its path in that slicer's entry:

- **macOS** (the `.app`): `"Snapmaker Orca": "/Applications/Multi Nozzle Size Orca.app"`
- **Windows** (the `.exe`, with doubled backslashes or forward slashes): `"OrcaSlicer": "D:/Tools/OrcaSlicer/orca-slicer.exe"`

Changes take effect the next time you open the dialog; no restart needed. If a slicer can't be found when sending, the add-in shows the path it tried. (The older `"orca_executable"` setting still works for Snapmaker Orca.)

The add-in exports STL files, or colored OBJ/3MF files when colors are applied (see [Sending Colors](#sending-colors)).

</details>

### Development <a name="development"></a>

The add-in's logic is tested offline against a stubbed Fusion API, on Windows, macOS and Linux, by [GitHub Actions](https://github.com/TUNA-THE-FIRST/FusionSlicerExporter/actions/workflows/tests.yml). To run the tests yourself (Python 3.14, no other dependencies):

```bash
python3 tests/offline/test_entry.py
python3 tests/offline/test_color.py
python3 tests/offline/test_windows.py
```

`tests/FusionSlicerExporterSelfTest` and `tests/FusionSlicerExporterColorReport` are Fusion scripts that check the color export inside a real Fusion. Releases: bump `version` in `FusionSlicerExporter.manifest`, commit, and push a matching tag such as `v1.3.0`; GitHub then tests the code, builds the zips with `tools/make_release.py` and publishes the release.

### Contact <a name="contact"></a>

Questions, bugs or ideas: please [open an issue](https://github.com/TUNA-THE-FIRST/FusionSlicerExporter/issues).

### Credits <a name="credits"></a>

Fusion Slicer Exporter is based on [ClickNSend](https://github.com/bankh/Fusion360_ClickNSend) by Sinan Bank (MIT License), which provided the original one-click export to Orca Slicer. This version adds macOS support, multiple slicers, color export, and a new icon.

### References and Other Software Tools <a name="references-and-other-software-tools"></a>

- [Fusion 360](https://www.autodesk.com/products/fusion-360/overview) - 3D CAD, CAM, and CAE software.  
- [Fusion 360 API](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-A92A4B10-3781-4925-94C6-47DA85A4F65A) - Documentation of Application Programming interface of Fusion 360.  
- [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer) - A 3D printing slicer based on Bambu Studio, PrusaSlicer, and SuperSlicer.
- [Snapmaker Orca](https://github.com/Snapmaker/OrcaSlicer) - Snapmaker's OrcaSlicer fork.
- [Bambu Studio](https://github.com/bambulab/BambuStudio) - Bambu Lab's slicer.
- [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) - Prusa Research's slicer.
- [Create A Custom Add-in To Send To 3D Print Utility](https://www.youtube.com/watch?v=9tiyAdgTzyI) - Similar Add-In for single body/ component import.



