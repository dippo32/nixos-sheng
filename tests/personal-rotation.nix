# Configuration and mocked KScreen protocol checks, not a hardware rotation test.
{
  flake,
  system ? "x86_64-linux",
}:
let
  c = flake.nixosConfigurations.sheng-kde-personal.config;
  unit = c.systemd.user.services.sheng-enable-rotation;
  pkgs = flake.inputs.nixpkgs.legacyPackages.${system};
in
assert c.services.desktopManager.plasma6.enable;
assert unit.wantedBy == [ "plasma-workspace-wayland.target" ];
assert builtins.elem "plasma-kwin_wayland.service" unit.after;
assert builtins.elem "graphical-session.target" unit.after;
assert unit.partOf == [ "graphical-session.target" ];
assert unit.unitConfig.ConditionUser == c.sheng.desktop.userName;
assert unit.serviceConfig.Type == "exec";
assert !(unit.serviceConfig ? RemainAfterExit);
assert unit.serviceConfig.TimeoutStartSec == "10s";
assert unit.serviceConfig.TimeoutStopSec == "5s";
assert unit.serviceConfig.RuntimeMaxSec == "6min";
assert !(unit.serviceConfig ? Restart);
assert builtins.match ".*/bin/sheng-enable-rotation" unit.serviceConfig.ExecStart != null;
assert !(flake.nixosConfigurations.sheng-kde.config.systemd.user.services ? sheng-enable-rotation);
assert c.services.shengFirmware.enable;
assert builtins.elem "multi-user.target" c.systemd.services.iio-sensor-proxy.wantedBy;
{
  internalOnly = true;
  policy = "always";
  boundedSessionSetup = true;
  runtimeRotationTested = false;

  scriptTests =
    pkgs.runCommand "sheng-personal-rotation-tests"
      {
        nativeBuildInputs = [
          pkgs.bash
          pkgs.coreutils
          pkgs.jq
          pkgs.python3
        ];
        ROTATION_HELPER = ../scripts/sheng-enable-rotation;
      }
      ''
        python3 <<'PY'
        import copy
        import json
        import os
        import pathlib
        import subprocess
        import sys
        import tempfile
        import unittest

        class Rotation(unittest.TestCase):
            def setUp(self):
                self.tmp = tempfile.TemporaryDirectory()
                self.addCleanup(self.tmp.cleanup)
                self.root = pathlib.Path(self.tmp.name)
                self.state = self.root / "state.json"
                doctor = self.root / "kscreen-doctor"
                # Build sandboxes need the actual Nix interpreter, not /usr/bin/env.
                doctor.write_text(f"""#!{sys.executable}
        import json,os,pathlib,sys
        p=pathlib.Path(os.environ['ROTATION_TEST_STATE'])
        s=json.loads(p.read_text())
        if sys.argv[1:] == ['--json']:
            n=s['reads']; s['reads']+=1
            value=s['snapshots'][min(n,len(s['snapshots'])-1)] if s['snapshots'] else s['config']
            p.write_text(json.dumps(s))
            print(value if isinstance(value,str) else json.dumps(value))
            sys.exit(s.get('query_exit',0))
        s['writes'].append(sys.argv[1:])
        if s.get('apply',True):
            for arg in sys.argv[1:]:
                for output in s['config'].get('outputs',[]):
                    if arg == 'output.'+output['name']+'.autoRotatePolicy.always':
                        output['autoRotatePolicy']=2
        p.write_text(json.dumps(s))
        sys.exit(s.get('apply_exit',0))
        """)
                doctor.chmod(0o755)
                sleeper = self.root / "sleep"
                sleeper.write_text(f"""#!{sys.executable}
        import json,os,pathlib,sys
        p=pathlib.Path(os.environ['ROTATION_TEST_STATE'])
        s=json.loads(p.read_text());s['sleeps'].append(sys.argv[1:]);p.write_text(json.dumps(s))
        """)
                sleeper.chmod(0o755)

            def panel(self, name="DSI-1", **updates):
                result = dict(id=1, name=name, type=7, connected=True, enabled=True,
                              currentModeId="0", autoRotatePolicy=1, rotation=1,
                              scale=1.75, pos=dict(x=0,y=0))
                result.update(updates)
                return result

            def run_helper(self, outputs, **updates):
                initial=dict(config=dict(outputs=outputs), snapshots=[], reads=0,
                             writes=[], sleeps=[])
                initial.update(updates)
                self.state.write_text(json.dumps(initial))
                env=os.environ.copy()
                env['PATH']=str(self.root)+os.pathsep+env['PATH']
                env['ROTATION_TEST_STATE']=str(self.state)
                result=subprocess.run(['bash',os.environ['ROTATION_HELPER']],env=env,
                                      text=True,capture_output=True,timeout=20)
                return result,json.loads(self.state.read_text())

            def test_internal_only_preserves_other_settings(self):
                panel=self.panel()
                external=self.panel('DP-1',id=2,type=14)
                inactive=self.panel('eDP-1',id=3,enabled=False)
                detached=self.panel('LVDS-1',id=4,connected=False)
                before=copy.deepcopy([external,panel,inactive,detached])
                result,state=self.run_helper(before)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(state['writes'],[['output.DSI-1.autoRotatePolicy.always']])
                expected=copy.deepcopy(before);expected[1]['autoRotatePolicy']=2
                self.assertEqual(state['config']['outputs'],expected)
                self.assertEqual(state['sleeps'],[])

            def test_optional_enabled_is_valid_and_all_panel_names_supported(self):
                for name in ['DSI-1','eDP-1','LVDS-1']:
                    with self.subTest(name=name):
                        panel=self.panel(name);del panel['enabled']
                        result,state=self.run_helper([panel])
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertEqual(state['writes'],[['output.'+name+'.autoRotatePolicy.always']])

            def test_already_enabled_does_not_write(self):
                result,state=self.run_helper([self.panel(autoRotatePolicy=2)])
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(state['writes'],[])
                self.assertEqual(state['reads'],1)

            def test_delayed_capability_waits_then_verifies(self):
                pending=self.panel();del pending['autoRotatePolicy']
                ready=self.panel()
                snapshots=[dict(outputs=[pending])]*3+[dict(outputs=[ready]),
                           dict(outputs=[self.panel(autoRotatePolicy=2)])]
                result,state=self.run_helper([ready],snapshots=snapshots)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(state['sleeps'],[['3']]*3)
                self.assertEqual(state['writes'],[['output.DSI-1.autoRotatePolicy.always']])

            def test_no_capability_no_active_or_ambiguous_never_writes(self):
                unsupported=self.panel();del unsupported['autoRotatePolicy']
                for outputs in [[unsupported],[self.panel(enabled=False)],
                                [self.panel(connected=False)],[self.panel(currentModeId="")],
                                [self.panel('HDMI-A-1',type=6)],
                                [self.panel(type=0)],
                                [self.panel(),self.panel('eDP-1',id=2)]]:
                    with self.subTest(outputs=outputs):
                        result,state=self.run_helper(outputs)
                        self.assertEqual(result.returncode,1)
                        self.assertEqual(state['writes'],[])
                        self.assertEqual(state['reads'],15)
                        self.assertEqual(state['sleeps'],[['3']]*14)

            def test_apply_zero_exit_does_not_claim_success_without_readback(self):
                result,state=self.run_helper([self.panel()],apply=False)
                self.assertEqual(result.returncode,1)
                self.assertEqual(len(state['writes']),15)
                self.assertEqual(state['reads'],30)
                self.assertEqual(state['sleeps'],[['3']]*14)

            def test_query_errors_and_malformed_json_are_bounded(self):
                for updates in [dict(query_exit=1),dict(snapshots=['not json']),
                                dict(snapshots=[dict(outputs='invalid')])]:
                    with self.subTest(updates=updates):
                        result,state=self.run_helper([self.panel()],**updates)
                        self.assertEqual(result.returncode,1)
                        self.assertEqual(state['writes'],[])
                        self.assertEqual(state['reads'],15)
                        self.assertEqual(state['sleeps'],[['3']]*14)

            def test_set_failure_is_bounded(self):
                result,state=self.run_helper([self.panel()],apply_exit=1,apply=False)
                self.assertEqual(result.returncode,1)
                self.assertEqual(len(state['writes']),15)
                self.assertEqual(state['reads'],15)
                self.assertEqual(state['sleeps'],[['3']]*14)

        unittest.main()
        PY
        touch "$out"
      '';
}
