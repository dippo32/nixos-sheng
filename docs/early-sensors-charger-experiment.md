# Early sensors during charger mode: candidate

On one sheng tablet, a cold charger boot left SSC unavailable after a long
Power press entered the desktop. `ssccli` reported that SSC QMI service 400
was absent; SensorProxy had no accelerometer and the KDE rotation helper
exhausted its retries. Restarting only the userspace RPC and sensor-proxy
services did not restore it. The ADSP had started roughly 160 seconds before
the registry and sensors RPC service. In an earlier ordinary boot, the sensor
RPC service started roughly one second after ADSP startup, and the sensor
proxy found sensor data. This timing supports, but does not prove, an ordering
problem.

This personal-profile-only candidate lets the existing registry and RPC units
start before `basic.target`, in parallel with the charger UI. The charger
wants, but neither requires nor waits for, the sensor daemon. A FastRPC udev
event also requests the daemon if its initial device-presence condition was
checked too early. Registry storage is still mounted first; shutdown ordering
is explicit. Failure of these services must not prevent the charger UI.

CI checks configuration and a representative systemd graph. It does not
recreate the entire NixOS startup transaction, delayed firmware, power usage,
or actual SSC QMI registration. Before deployment validate the generated units
and check for ordering cycles; on a candidate generation verify cold charger
boot, battery display and charging, short and long Power, unplug, SSC service
400, `HasAccelerometer`, actual rotation, audio, and rollback. Starting the
sensor daemon during charging may affect idle power and must be measured. Do
not reset the live ADSP merely to make the desktop rotate: audio and power
services share it.
