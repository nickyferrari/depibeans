# Basement manual light controls

The Lights · Manual tab is limited to `depi-two` (DEPI 02) and `depi-five`
(DEPI 04). It addresses SmartLight firmware candidates 1–26 and uses address 0
for all lights. These are not detected or verified physical rails. Operators
can save physical rail labels on each controller while identifying the wiring.

Commands use the existing calibrated intensity packet, FPGA pins 0/1, profile
initial mask, clock, and 0–100 controller-unit bounds. No raw DAC writes,
calibration changes, alternate bus, or choke-pin guesses are exposed. A rail
with missing calibration, a different receiver protocol, or no power may not
respond. The bus has no acknowledgement readback; cards show the last command,
never a claimed measured on/off state.

`depibeans.basement_control` extends each machine's installed ControlDesk.
It retains its original controller implementation and profile. Commands share
its run and hardware locks, reject active camera/experiment work, record a
unique ID before hardware access, and never automatically retry. Outcomes and
labels are kept in the controller's data directory. Service restarts do not
send light commands.

Deploy the new module and the matching tracked systemd drop-in with the release
helper. Link the drop-in as `depibeans-control.service.d/30-manual-lights.conf`,
reload systemd, and restart only an idle basement controller. Publish app.js and
style.css on Walker hosting after both backend services are available.

Rollback: remove that drop-in link, reload systemd, restart the idle controller,
then roll back the deployment receipt. Original ExecStart and profiles remain
unchanged beneath the drop-in. Restore hosted assets using the hosting receipt.

No automated or hardware actuation tests were run for this release, as requested.
Release syntax/hash checks and read-only service/status checks are separate from
physical acceptance, which remains with the operator.
