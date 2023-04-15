# zpool-events

This is a small script for sending notifications (e.g. via email or https://ntfy.sh) when a ZFS event occurs, such as a read error, checksum failure, or a degraded zpool.

## Usage

The script runs continuously and executes a file "send_zpool_status.sh" when an event occurs. It filters out uninteresting events (e.g. sysevent.fs.zfs.history_event, sysevent.fs.zfs.scrub_start) and has limits on how often it will send notifications.

To use the script, you need to put the files in /root/zpool-events and create a file called "send_zpool_status.sh" that is executable in that directory. The file should send the arguments given, perhaps together with the status of the zpools, as a notification or email or whatever you want. For example, you can use a file like this:

```sh
#!/bin/sh

nl='
'
status="$*${nl}$(zpool list -H | cut -f1,10 | tr \\t ' ')"
curl -H "Title: ZFS" -H "Tags: warning" -d "$status" ntfy.sh/mytopic
```

(where you would replace "mytopic" with a private topic name of your choice).

You also need to start the Python file as a service. In Debian, you can use the following commands:

```sh
ln -s /root/zpool-events/zpool-events.service /etc/systemd/system/zpool-events.service
sudo systemctl daemon-reload
sudo systemctl restart zpool-events
```

## License

Unlicense, do whatever you want with it.
