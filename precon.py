import dpkt
from datetime import datetime

import pcap
import os
import select
import sys


def list_to_num(x):
    total = 0

    for digit in x:
        total = total * 256 + ord(digit)

    return total


def list_to_host(x):
    return '.'.join([str(ord(y)) for y in x])


def list_to_host6(x):
    assert len(x) == 16

    return ':'.join([''.join([hex(ord(x[i])).split('x')[-1], hex(ord(x[i+1])).split('x')[-1]]) for i in xrange(0, 16, 2)])


def register_host(ip):
    if ip not in hosts.keys():
        print "Found new host %s" % ip
        hosts[ip] = dict()

    # insert time here
    now = datetime.now()
    day = now.strftime("%B%d")
    hour = now.strftime("%H")

    if day not in date_range:
        date_range.append(day)

    if "Time" not in hosts[ip].keys():
        hosts[ip]["Time"] = dict()

    if day not in hosts[ip]["Time"]:
        hosts[ip]["Time"][day] = list()

    if hour not in hosts[ip]["Time"][day]:
        hosts[ip]["Time"][day].append(hour)


def register_port(ip, port, proto, server):
    if "Ports" not in hosts[ip].keys():
        hosts[ip]["Ports"] = dict()

    if str(port) + '/' + proto not in hosts[ip]["Ports"].keys():
        print "Found new Port %s: %s %s" % (ip, str(port) + '/' + proto, server)
        newline = True
        hosts[ip]["Ports"][str(port) + '/' + proto] = server


def parse_bnet(ip, data):
    fields = data.split(',')

    if len(fields) != 10:
        raise WritePcap

    # uid = fields[3]
    account = fields[4] + '#' + fields[5]

    if 'tags' not in hosts[ip].keys():
        hosts[ip]['tags'] = list()

    if account not in hosts[ip]['tags']:
        print "Discovered Battle Net Account for %s, %s" % (ip, account)
        hosts[ip]['tags'].append(account)

    # The following lines are for assisting in reverse engineering the protocol

    # fields[0] is unknown
    # fields[1] is some user/session dependant number between 968472 and 307445411
    # fields[2] is unknown
    # fields[3] is likely the UID
    # fields[4] is user name
    # fields[5] is unique username number
    # fields[6] is unknown
    # fields[7] is Region
    # fields[8] is unknown
    # fields[9] is a rather peculiar value whose MSB changes more than the LSB


def parse_mdns_name(data, offset):
    name = list()
    length = 1
    pos = offset

    while length != 0:
        length = data[pos]
        name.append(data[pos+1:pos+1+length])

    return '.'.join(name), offset+1


def parse_mdns(ip, data):
    # print 'M',

    raise WritePcap  # Still working on this dissector

    if ord(data[3]) != 0x84:
        # Not an authortive response packet
        return

    offset = 12

    while True:
        if ord(data[offset]) < 0xc0:
            name, offset = parse_mdns_name(data, 12)
            print name
        else:
            offset = offset + 2

        rtype = list_to_num(data[offset:offset+2])

        offset = offset + 2

        if rtype == 12:
            offset = offset + 6
        elif rtype == 16:
            offset = offset + 8
        elif rtype == 33:
            offset = offset + 8
        else:
            print "New rtype"
            raise WritePcap

        length = ord(data[offset])

        while length != 0:
            if length < 0xc0:
                offset = offset + 1
                print data[offset:offset+length]
                offset = offset + length
            else:
                offset = offset + 2


def parse_ssdp(ip, data):
    url = ''
    proto = "unk"
    port = None
    server = ''
    device = list()
    user_agent = ''
    extras = list()

    newline = False

    ssrp = data.splitlines()
    method = ssrp[0].split(' ')[0]

    if method not in ["NOTIFY", "M-SEARCH"]:
        print "SSRP: Unknown method: %s" % method
        raise WritePcap

    for line in ssrp[1:]:
        if ": " in line:
            field = line.split(': ')
        else:
            field = line.split(':')

        if field[0].upper() in ["HOST", "MAN", "CACHE-CONTROL", "NTS", "USN", "MX", "ST", 'OPT', '01-NLS', 'DATE', '']:
            continue

        if field[0].upper() == "LOCATION":
            if ": " in line:
                url = field[1]
            else:
                url = ':'.join(field[1:])

            if url[:4] == "http":
                proto = "tcp"

            if ip in line:
                if len(line.split(ip)) == 2 and line.split(ip)[1][0] == ':':
                    port = line.split(ip)[1].split('/')[0][1:]
                else:
                    print "SSRP IP split = %s" % line.split(ip)

            if port is None:
                if url[:4] == "http":
                    if url[4] == 's':
                        port = 443
                    else:
                        port = 80
                else:
                    print "SSRP Unknown Protocol: %s" % url
                    raise WritePcap

        elif field[0].upper() == "SERVER":
            if field[1][:17] == "Microsoft-Windows":
                win_ver = field[1][18:21]

                if win_ver == "5.0":
                    device.append("Windows 2000")
                elif win_ver == "5.1":
                    device.append("Windows XP")
                elif win_ver == "5.2":
                    device.append("Windows XP Professional x64")
                elif win_ver == "6.0":
                    device.append("Windows Vista")
                elif win_ver == "6.1":
                    device.append("Windows 7")
                elif win_ver == "6.2":
                    device.append("Windows 8")
                elif win_ver == "6.3":
                    device.append("Windows 8.1")
                elif field[1][18:22] == "10.0":
                    device.append("Windows 10")
                else:
                    print "Unknown windows version %s" % field[1]
                    raise WritePcap
            server = field[1]
        elif field[0] == "NT":
            if "device:" in field[1]:
                device.append(field[1].split("device:")[1].split(':')[0])
        elif field[0].upper() == "USER-AGENT":
            user_agent = field[1]

            if user_agent[:13] == "Google Chrome":
                device.append(user_agent.split(' ')[2])
                user_agent = ' '.join(user_agent.split(' ')[:2])
        elif field[0].upper()[:2] == "X-":
            extras.append(field)
        elif field[0].upper() == "CONSOLENAME.XBOX.COM":
            device.append(field[1])
        else:
            print "Unknown SSRP Field: %s:%s" % (field[0], field[1:])
            raise WritePcap

    # parsing done, now time to store the results

    if url != '':
        if "URLs" not in hosts[ip].keys():
            hosts[ip]["URLs"] = list()

        if url not in hosts[ip]["URLs"]:
            print "Found new URL %s: %s" % (ip, url)
            newline = True
            hosts[ip]["URLs"].append(url)

    if port is not None:
        register_port(ip, port, proto, server)

    if len(device) > 0:
        if "Device" not in hosts[ip].keys():
            hosts[ip]["Device"] = list()

        for devtype in device:
            if devtype not in hosts[ip]["Device"]:
                print "Found new Device Type %s: %s" % (ip, devtype)
                newline = True
                hosts[ip]["Device"].append(devtype)

    if user_agent != '':
        if "UserAgent" not in hosts[ip].keys():
            hosts[ip]["UserAgent"] = list()

        if user_agent not in hosts[ip]["UserAgent"]:
            print "Found new User Agent: %s, %s" % (ip, user_agent)
            newline = True
            hosts[ip]["UserAgent"].append(user_agent)

    for extra in extras:
        if "Extras" not in hosts[ip].keys():
            hosts[ip]["Extras"] = list()

        if extra not in hosts[ip]["Extras"]:
            print "Found new SSRP Extra: %s, %s" % (ip, extra)
            newline = True
            hosts[ip]["Extras"].append(extra)

    if newline:  # Done printing updates
        print ''


def parse_teredo(ip, data):
    if 0x70 < ord(data[0]) or ord(data[0]) < 0x60:
        print "Teredo is version %d" % ord(data[0])
        raise WritePcap

    if list_to_num(data[1:5]) != 0:
        print "Teredo has a flow label"
        raise WritePcap

    if ord(data[6]) != 59:
        print "Teredo has a next header"
        raise WritePcap

    if data[24:40] != '\xff\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01':
        print "Teredo not a multicast packet: %s" % repr(data[24:40])
        raise WritePcap

    ipv6 = list_to_host6(data[8:24])  # Todo: support ipv6 in the future
    tun_server = list_to_host(data[12:16])
    tun_client_port = list_to_num([chr(0xff - ord(x)) for x in data[18:20]])
    tun_client = list_to_host([chr(0xff - ord(x)) for x in data[20:24]])

    if tun_client != ip and tun_client not in hosts.keys():
        print "Discovered external ip: %s" % tun_client
        register_host(tun_client)

    register_port(tun_client, tun_client_port, 'udp', '')

    if "endpoints" not in hosts[ip].keys():
        hosts[ip]["endpoints"] = list()

    if tun_server not in hosts[ip]["endpoints"]:
        print "Discovered new Teredo Server: %s" % tun_server
        hosts[ip]["endpoints"].append(tun_server)


def report():
    timeline = ''

    for hour in xrange(0, 24):
        if len(str(hour)) > 1:
            timeline = timeline + " " + str(hour)
        else:
            timeline = timeline + "  " + str(hour)

    print ''

    for host in hosts.keys():
        print host

        if "Time" in hosts[host].keys():
            timeline_padding = 0

            for day in date_range:
                if len(str(day)) > timeline_padding:
                    timeline_padding = len(str(day))

            print ' ' * timeline_padding + timeline

            for day in date_range:
                if day in hosts[host]["Time"].keys():
                    usage = ""
                    print day,
                    print "-" * (timeline_padding - len(str(day))),

                    for hour in xrange(0, 24):
                        time = str(hour)

                        if len(time) == 1:
                            time = '0' + time

                        if time in hosts[host]["Time"][day]:
                            mark = 'X'
                        else:
                            mark = ' '

                        usage = usage + mark + '  '

                    print usage

        for data in hosts[host].keys():
            if data is not "Time":
                print data

                for record in hosts[host][data]:
                    print record

        print ''

class WritePcap(Exception):
    pass


ip_hdr = 14

hosts = dict()  # stores all the recon data. Currently no way to retrieve data
date_range = list()


# Setup Artificial Ignorance. Not sure what that is? Google Artificial Ignorance Marcus Ranum
ignorance_filename = 'ai_log.pcap'

if os.path.isfile(ignorance_filename):
    os.remove(ignorance_filename)

pcap_log = file(ignorance_filename, 'wb')
ignorance = dpkt.pcap.Writer(pcap_log)

sniffer = pcap.pcap()
sniffer.setfilter("udp and ip multicast")

print "ready.."

try:
    for ts, pkt in sniffer:
        r, w, e = select.select([sys.stdin], [], [], 0)  # detect if enter was pressed
        if len(r) > 0:
            sys.stdin.readline()  # clear the return
            report()

        if [ord(pkt[12]), ord(pkt[13])] != [8, 0]:
            # print "Not an IP packet"
            ignorance.writepkt(pkt, ts)
            continue

        ip_sz = (ord(pkt[ip_hdr]) - 0x40) * 4
        pkt_sz = list_to_num(pkt[ip_hdr + 2: ip_hdr + 4])

        if len(pkt) != pkt_sz + 14:
            # print "Size mismatch (reported %d, actual %d)" % (pkt_sz + 14, len(pkt))
            ignorance.writepkt(pkt, ts)
            continue

        if ord(pkt[ip_hdr + 6]) not in [0, 0x40]:
            # print "Fragmented %d" % ord(pkt[ip_hdr + 6])
            ignorance.writepkt(pkt, ts)
            continue

        if ord(pkt[ip_hdr + 9]) != 17:
            # print "Not a UDP packet"
            ignorance.writepkt(pkt, ts)
            continue

        src_host = list_to_host(pkt[ip_hdr + 12:ip_hdr + 16])

        register_host(src_host)

        udp_hdr = ip_hdr + ip_sz

        svc_port = list_to_num(pkt[udp_hdr + 2: udp_hdr + 4])

        try:
            if svc_port in [67, 68]:
                raise WritePcap
                # I'll get around to this soon
            elif svc_port == 1228:
                parse_bnet(src_host, pkt[udp_hdr + 8:])
            elif svc_port == 1900:
                parse_ssdp(src_host, pkt[udp_hdr + 8:])
            elif svc_port == 3544:
                # Teredo IPv6 over UDP tunneling
                parse_teredo(src_host, pkt[udp_hdr + 8:])
            elif svc_port == 3702:
                # WS-Discovery - Generally looking for WSD enabled (HP) printers
                raise WritePcap
            elif svc_port == 5353:
                parse_mdns(src_host, pkt[udp_hdr + 8:])
            elif svc_port == 5355:
                raise WritePcap
                # Link Local Name Resolution, but unlike mDNS responses are sent unicast
            elif svc_port == 7765:
                raise WritePcap
                # WonderShare MobileGo.
                # Used to manage android phone, not really interesting except to retrieve operating system and computer name
            else:  # Artificial Ignorance Catch
                # print "%s:%d" % (src_host, svc_port)
                raise WritePcap
        except WritePcap:
            # print "!",
            ignorance.writepkt(pkt, ts)
except KeyboardInterrupt:
    report()
