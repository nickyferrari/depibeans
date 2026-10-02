# Legacy behavior parity tracker

Scope: reproduce the full deployed DEPI application in Python, including lighting calibration, acquisition, experiment execution, chamber control and data handling. NetBeans is the Java development environment; the target is application behavior, not rebuilding the NetBeans IDE. Native vendor drivers and FPGA/microcontroller firmware remain supported hardware dependencies.

This is an initial source-backed capability map, not a claim of exhaustive semantic review or completed migration. The working fleet PC remains the authority for deployed versions and settings. Archived variants must be reconciled before declaring full parity.

| Capability | Legacy evidence | Python location | Current evidence | Acceptance still required |
|---|---|---|---|---|
| Raw lighting and blackout | [SmartlightController.java](../legacy-reference/DEPI/phenomics-cc-mk9000/src/PhenoSystemControl/control/lights/SmartlightController.java) | depibeans/lighting.py; hardware.py; desktop.py | Implemented; broadcast and desktop light response confirmed | Verify every physical rail and zone address |
| Lighting calibration | [CalibratedLightController.ino](../legacy-reference/Calibratron/Lighting%20Calibratron%20v1.2/firmware/CalibratedLightController/CalibratedLightController.ino) | depibeans/calibration.py; desktop.py | Implemented; hardware calibration not validated | Known-good coefficients, light meter, measured fit and controlled upload |
| FPGA timing and trigger execution | [ProtocolEngine.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/resource/fpga/ProtocolEngine.java) | hardware.py implements lighting waveform execution only | Lighting execution verified; experiment compiler remains | Actual FPGA profile, pin assignments, camera timing requirements and instrumented trigger comparison |
| Camera protocol fields, pulses and flashes | [CameraProtocol.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/cameras/CameraProtocol.java) | Not ported | Source mapped; not hardware enabled | Exposure, frame intervals, measuring pulses, saturation and shutter timing parity |
| Hitachi camera acquisition | [HitachiCameraDriver.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/cameras/HitachiCameraDriver.java) | Not ported | Camera not identified on testbed | Working runtime, camera identity, transport, SDK and frame capture |
| AVT camera acquisition | [AVTCameraDriver.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/cameras/AVTCameraDriver.java) | Not ported | Camera not identified on testbed | Installed SDK and deployed driver protocol; acquisition and metadata comparison |
| CS camera acquisition | [CSCameraDriver.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/cameras/CSCameraDriver.java) | Not ported | Source exists; deployment unknown | Identify whether fleet uses this camera family |
| Temperature/humidity chamber interface | [BigfootServerHandle.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/resource/BigfootServerHandle/BigfootServerHandle.java) | Not ported | Archived constructor throws UnsupportedOperationException | Working fleet controller implementation, endpoint, limits and measurements |
| Temperature driver | [BigfootTemperature.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/driver/BigfootDrivers/BigfootTemperature.java) | Not ported | This archived class is empty and deprecated | Recover deployed working implementation before defining parity |
| Experiment engine and resume behavior | [GenericEventControlStructure.java](../legacy-reference/DEPI/william-lordc/ControlEngine/src/main/java/edu/msu/prl/PhenomicsControl/Engine/control/GenericEventControlStructure.java) | core.py is a separate simulator engine | Full legacy engine parity not established | Capture real configurations, experiment timelines, ownership and restart behavior |
| Scripted experiment protocols | [ScriptedCameraProtocol.java](../legacy-reference/DEPI/william-lordc/PhenoScript/src/main/java/edu/msu/prl/PhenomicsControl/Script/parser/javascript/ScriptedCameraProtocol.java) | Not ported | Source mapped | Representative scripts and supported language semantics; bounded Python execution |
| Image upload and synchronization | [FileSync.java](../legacy-reference/DEPI/william-lordc/PhenoUpload/src/main/java/edu/msu/prl/PhenomicsControl/Upload/Sync/FileSync.java) | Not ported | Source mapped | Destinations, naming, metadata, retries and existing backlog handling |
| Experiment analysis/reporting | [PostAnalysis.java](../legacy-reference/DEPI/william-lordc/PostAnalysis/src/main/java/edu/msu/prl/PostAnalysis/PostAnalysis.java) | Not ported | Source mapped | Reference experiment data and expected reports |
| Notifications | [EmailWarner.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/warner/EmailWarner.java) | Not ported | Source mapped | Configured recipients, triggers and authenticated delivery; no messages sent during mapping |
| Filter changer | [FilterChanger_Factory.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/driver/FilterChanger/FilterChanger_Factory.java) | Not ported | Factory marked deprecated/not implemented | Confirm any physical filter changer and actual operating implementation |
| Sensor health/checks | [PiSensorChecker_Factory.java](../legacy-reference/DEPI/william-lordc/ControlCenter/src/main/java/edu/msu/prl/PhenomicsControl/ControlSystem/control/checker/PiSensorChecker_Factory.java) | Not ported | This archived factory is empty | Actual sensor inventory and live fleet health path |

## Portal and fleet additions

Authenticated Walker website access, per-chamber permissions, real 24-chamber inventory, stale/offline health, physical scheduling, command audit and recovery remain required. Simulator entries and schedules do not establish physical fleet operation.

## Testbed device inspection

Read-only Windows inspection on September 11 reports the Nexys2/Digilent USB interface, AVRISP mkII and COM1 (ACPI\PNP0501\1, RS232 Serial Port). COM1 being present does not establish a connected instrument. No matching COM1/SerialPort/jssc/gnu.io references were found in the searched extracted Java, firmware and configuration files; the full archive and fleet runtime may differ.

The FPGA is already used by Python for lighting; camera/flash pins must be mapped before enabling additional waveforms. AVRISP is a firmware maintenance device, not an extra actuator or camera. Programmer enumeration does not identify target MCU, target power or firmware. No firmware, fuses, EEPROM or serial-port settings were changed during this inspection.

## Completion evidence required

Each deployed capability needs its actual legacy version/configuration, Python implementation, reference behavior comparison, physical observation or sensor/frame evidence, restart/disconnect behavior and rollback procedure. A successful build or FPGA completion alone is insufficient.
