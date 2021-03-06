"""
Master Thesis
Network Monitoring and Attack Detection

csv_labeller.py
Functions used to label the .csv files holding the features generated by the FLowMeter and KDD feature-extraction tools


@author: Nicolas Kaenzig, D-ITET, ETH Zurich
"""

import ipaddress
import os
import json
import csv
import pickle
import bro_misc
from datetime import datetime, timedelta
from joblib import Parallel, delayed


def csv_label_malicious_sessions(csv_path, extracted_path, malicious_ips_path, malicious_sessions_path, mode='FlowMeter'):
    """
    Function used for the "sessions-labelling". Writes labelled data to a new .csv with suffix "-normalSess".
    In addition, the malicious flows are written also to a seperate file with suffix "-maliciousSess" and the
    normal flows to a file with suffix "-labelledSess"

    :param csv_path: Path to the .csv file to be labelled
    :param extracted_path: Path to directory where mapping_dicts.pickle is located. (generated in bro_main.py)
    :param malicious_ips_path: Path to the .json file holding all malicious IPs
    :param malicious_sessions_path: Path to the malicious sessions .json file as generated by cs_report_parser.py
    :param mode: Set to 'FlowMeter' or 'KDD'
    """
    normal_samples_path = os.path.join(os.path.dirname(csv_path), os.path.basename(os.path.splitext(csv_path)[0]) + '-normalSess.csv')
    malicous_samples_path = os.path.join(os.path.dirname(csv_path), os.path.basename(os.path.splitext(csv_path)[0]) + '-maliciousSess.csv')
    labelled_samples_path = os.path.join(os.path.dirname(csv_path), os.path.basename(os.path.splitext(csv_path)[0]) + '-labelledSess.csv')

    nr_labeled = 0
    nr_flows = 0
    year = '2017'

    with open(os.path.join(extracted_path, 'mapping_dicts.pickle'), 'rb') as fp:
        mapping_dicts = pickle.load(fp)

    with open(malicious_ips_path, 'r') as fp:
        malicious_ips = json.load(fp)['malicious_ips']

    with open(malicious_sessions_path, 'r') as fp:
        malicious_sessions = json.load(fp)

    with open(csv_path, 'r') as csv_r, open(normal_samples_path, 'w') as csv_norm_w, open(malicous_samples_path, 'w') as csv_mal_w, open(labelled_samples_path, 'w') as csv_w:
        csv_reader = csv.reader(csv_r, delimiter=',', quotechar='#')
        csv_norm_writer = csv.writer(csv_norm_w, delimiter=',', quotechar='#')
        csv_mal_writer = csv.writer(csv_mal_w, delimiter=',', quotechar='#')
        csv_writer = csv.writer(csv_w, delimiter=',', quotechar='#') # TODO: remove

        header = csv_reader.__next__()
        src_ip_idx = header.index('Src IP')
        dst_ip_idx = header.index('Dst IP')

        csv_date_format = '%d/%m/%Y %H:%M:%S' # 26/04/2017 02:02:56
        if mode == 'FlowMeter':
            timestamp_idx = header.index('Timestamp')
        elif mode == 'KDD':
            timestamp_idx = header.index('conn_end_time')
            csv_date_format = '%Y-%m-%dT%H:%M:%S'# 2017-04-26T02:02:56

        add_label_column = False
        if 'Label' not in header:
            header.append('Label')
            add_label_column = True
        label_idx = header.index('Label')

        csv_norm_writer.writerow(header)
        csv_mal_writer.writerow(header)
        csv_writer.writerow(header)


        for row in csv_reader:
            if (nr_flows % 100000 == 0):
                print('{} flows parsed; {} labelled'.format(nr_flows, nr_labeled))

            if row[src_ip_idx] not in malicious_ips and row[dst_ip_idx] not in malicious_ips:
                if add_label_column:
                    row.append('0')
                else:
                    row[label_idx] = '0'
                nr_flows += 1
                csv_norm_writer.writerow(row)
                csv_writer.writerow(row) #TODO: remove
                continue


            for pid, sessions in malicious_sessions.items():
                labelled = False
                for session in sessions:
                    # print('Labeling session {} ...'.format(pid))

                    # convert times to suitable format for datemath: dd/mm/yyyy HH:mm:ss
                    start_time = '{}/{} {}:00'.format(session['start_date'], year, session['start_time']) # '%Y-%m-%dT%H:%M:%S'
                    end_time = '{}/{} {}:00'.format(session['end_date'], year, session['end_time'])

                    start_time = datetime.strptime(start_time, '%d/%m/%Y %H:%M:%S')
                    end_time = datetime.strptime(end_time, '%d/%m/%Y %H:%M:%S')

                    # caution: FlowMeter generates times according to local timezone, while malicios_sessions stores UTC timeformat
                    UTC_OFFSET = 2
                    current_time = datetime.strptime(row[timestamp_idx], csv_date_format) - timedelta(hours=UTC_OFFSET)

                    session_malicious_ips = set()
                    malicious_hostnames = set()
                    for host in session['hosts']:
                        if bro_misc.check_if_valid_IP(host):
                            session_malicious_ips.add(host)
                        elif host in mapping_dicts['domain_to_ip_dict']:
                            session_malicious_ips = session_malicious_ips.union(mapping_dicts['domain_to_ip_dict'][host])
                            malicious_hostnames.add(host)
                        else:
                            # print('host {} in session {} could not be resolved to an ip'.format(host, pid))
                            malicious_hostnames.add(host)

                    if row[src_ip_idx] in session_malicious_ips or row[dst_ip_idx] in session_malicious_ips:
                        if current_time >= start_time and current_time <= end_time:
                            if add_label_column:
                                row.append('1')
                            else:
                                row[label_idx] = '1'
                            nr_labeled += 1
                            # print('session {} match'.format(pid))
                            labelled = True
                            break
                if labelled:
                    break

            if labelled:
                csv_mal_writer.writerow(row)
            else:
                if add_label_column:
                    row.append('1')
                else:
                    row[label_idx] = '0'
                csv_norm_writer.writerow(row)
            csv_writer.writerow(row) # TODO: remove

            nr_flows += 1

        print('{} flows out of {} were labelled as malicious ({})'.format(nr_labeled, nr_flows, nr_labeled * 100 / nr_flows))


def csv_label_malicious_ips(csv_path, malicious_ips_path, out_dir=None, mode='FlowMeter'):
    """
    Function used for "host-labelling"

    :param csv_path: Path to the .csv file to be labelled
    :param malicious_ips_path: Path to the .json file holding all malicious IPs
    :param out_dir: Directory where the new .csv should be written to. (Same directory if None)
    :param mode: Set to 'FlowMeter' or 'KDD'
    """
    if out_dir:
        labelled_samples_path = os.path.join(out_dir, os.path.basename(os.path.splitext(csv_path)[0]) + '-labelled.csv')
    else:
        labelled_samples_path = os.path.join(os.path.dirname(csv_path), os.path.basename(os.path.splitext(csv_path)[0]) + '-labelled.csv')

    nr_labeled = 0
    nr_flows = 0
    nr_src = 0
    nr_dst = 0
    skipped = 0
    add_label_column = False

    with open(malicious_ips_path, 'r') as fp:
        malicious_ips = json.load(fp)['malicious_ips']
    # convert to set for faster lookups
    malicious_ips = set(malicious_ips)

    with open(csv_path, 'r') as csv_r, open(labelled_samples_path, 'w') as csv_w:
        csv_reader = csv.reader(csv_r, delimiter=',', quotechar='#')
        csv_writer = csv.writer(csv_w, delimiter=',', quotechar='#')

        header = csv_reader.__next__()
        src_ip_idx = header.index('Src IP')
        dst_ip_idx = header.index('Dst IP')
        if mode == 'FlowMeter':
            prot_idx = header.index('Protocol')
            syn_cnt_idx = header.index('SYN Flag Cnt')
        elif mode == 'KDD':
            flag_idx = header.index('flag')
            valid_conn_states = set(['S1', 'S2', 'S3', 'SF', 'RSTO', 'RSTR'])
        if 'Label' in header:
            label_idx = header.index('Label')
        else:
            header.append('Label')
            add_label_column = True

        csv_writer.writerow(header)
        for row in csv_reader:
            nr_flows += 1
            if mode == 'FlowMeter':
                if row[prot_idx] == '6' and row[syn_cnt_idx] == '0':  # TODO: maybe remove this again
                    skipped += 1
                    continue
            elif mode == 'KDD':
                if row[flag_idx] not in valid_conn_states:
                    skipped += 1
                    continue

            if row[src_ip_idx] in malicious_ips or row[dst_ip_idx] in malicious_ips:
                if row[src_ip_idx] in malicious_ips:
                    nr_src +=1
                if row[dst_ip_idx] in malicious_ips:
                    nr_dst +=1

                if add_label_column:
                    row.append('1')
                else:
                    row[label_idx] = '1' # 1 encodes malicious, 0 encodes normal
                nr_labeled += 1
            else:
                if add_label_column:
                    row.append('0')
                else:
                    row[label_idx] = '0'
            csv_writer.writerow(row)

    print('{} flows out of {} were labelled as malicious ({}%)'.format(nr_labeled, nr_flows, nr_labeled*100/nr_flows))
    print('src: {}\ndst: {}'.format(nr_src, nr_dst))
    if mode == 'FLowMeter':
        print('{} ({}%) TCP-Flows skipped due to zero SYN count\n\n'.format(skipped, skipped*100.0/nr_flows))
    elif mode == 'KDD':
        print('{} ({}%) TCP-Flows skipped because of non-established state\n\n'.format(skipped, skipped*100.0/nr_flows))


def add_internal_external_feature_to_csv(csv_path, internal_prefixes):
    """
    Function used to add the Dst Int Ext feature to a FlowMeter .csv file.
    Note that this feature can also be generated by the FLowMeter tool directly.

    :param csv_path: Path of the FlowMeter .csv
    :param internal_prefixes: List of prefixes in CIDR format of the internal network
    """
    out_path = os.path.splitext(csv_path)[0] + '-intExt.csv'

    with open(csv_path, 'r') as csv_r, open(out_path, 'w') as csv_w:
        csv_reader = csv.reader(csv_r, delimiter=',', quotechar='#')
        csv_writer = csv.writer(csv_w, delimiter=',', quotechar='#')

        header = csv_reader.__next__()
        dst_ip_idx = header.index('Dst IP')
        label_idx = header.index('Label')

        new_header = header[:-1] + ['dstIntExt', 'Label']
        dstIntExt_idx = new_header.index('dstIntExt')

        internal = False

        csv_writer.writerow(new_header)
        for row in csv_reader:
            dst_ip = row[dst_ip_idx]

            for prefix in internal_prefixes:
                if ipaddress.ip_address(dst_ip) in ipaddress.ip_network(prefix):
                    row.insert(-1, '0') # '0' for internal IPs
                    internal = True
            if not internal:
                row.insert(-1, '1')  # '1' for external IPs

            internal = False

            csv_writer.writerow(row)


def label_multiple_files(csv_directory, malicious_ips_path):
    """
    Function used to label multiple files in a directory (host-labelling)

    :param csv_directory: Directory holding the .csvs
    :param malicious_ips_path: Path to the .json file holding all malicious IPs
    """
    filenames = os.listdir(csv_directory)
    out_dir = os.path.join(csv_directory, 'Labelled')

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    for filename in filenames:
        if filename.endswith(".csv"):
            filepath = os.path.join(csv_directory, filename)
            print('Labelling {} ...'.format(filepath))
            csv_label_malicious_ips(filepath, malicious_ips_path, out_dir=out_dir)


if __name__ == "__main__":
    extracted_path17 = './extracted/ls17'
    extracted_path18 = './extracted/ls18'

    malicious_ips_path17 = os.path.join(extracted_path17, 'malicious_ips.json')
    malicious_ips_path18 = os.path.join(extracted_path18, 'malicious_ips.json')
    malicious_sessions_path17 = os.path.join(extracted_path17, 'malicious_sessions.json')

    fm_csv_path17 = '/mnt/data/nicolas/workspace/Network_Analyzer/data/FlowMeter/ls17_Dup15/all-traffic24-ordered.pcap_Flow.csv'
    kdd_csv_path17 = '/mnt/data/nicolas/workspace/Network_Analyzer/data/KDD/ls17/kdd_features_ls17.csv'

    ### SESSION-LABELLING
    csv_label_malicious_sessions(fm_csv_path17, extracted_path17, malicious_ips_path17, malicious_sessions_path17, mode='FlowMeter')
    csv_label_malicious_sessions(kdd_csv_path17, extracted_path17, malicious_ips_path17, malicious_sessions_path17, mode='KDD')

    ### HOST-LABELLING
    csv_label_malicious_ips(fm_csv_path17, malicious_ips_path17, mode='FlowMeter')
    csv_label_malicious_ips(kdd_csv_path17, malicious_ips_path17, mode='KDD')