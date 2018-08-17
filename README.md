# Precon

Passive network reconnaissance relying on Multicast Protocols

## Plan

Create a set of parsers for multicast protocols such as mDNS and UPnP for
extracting environmental awareness and to use these findings to seed an Armitage
dashboard for red team engagements

* precon_priv - Sniffer based package the requires promisc permissions
* precon_user - Daemon based package that can run as any user

## Dependancies

Currently depends on

* pypcap
* dpkt

## Usage

With promisc privledges, run python precon.py

In the current state it'll print new information it's discovered.

Additionally it'll save an unparsed packets as ai_log.pcap

Outputs a summary report on exit, or hit return if you want a report without quiting