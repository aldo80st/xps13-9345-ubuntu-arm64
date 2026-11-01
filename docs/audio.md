# Speaker output, SoundWire and channel mapping

PipeWire and ALSA can enumerate hardware even when speaker playback is silent or channel mapping is wrong. Our observed sink reports four logical channels: `FL, FR, RL, RR`. This does **not** prove speakers are functioning correctly.

The [XPS Linux patches project](https://github.com/alexVinarskis/linux-x1e80100-dell-tributo) notes swapped L/R channels and directs users to ALSA UCM and Audioreach topology. [Ubuntu bug 2172596](https://mail-archive.com/ubuntu-bugs%40lists.ubuntu.com/msg6328103.html) reports SoundWire bus clashes on Ubuntu 26.10/7.3.

Check `wpctl status`, `wpctl inspect <sink-id>`, `aplay -l`, `journalctl -k -b | grep -iE 'soundwire|SWR bus|ASoC'` and test actual left and right output. Do not blindly replace UCM files.

**Status:** investigation, not resolved.
