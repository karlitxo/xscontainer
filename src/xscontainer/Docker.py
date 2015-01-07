import ApiHelper
import Util
import thread
import time
import simplejson

import ApiHelper


def _execute_cmd_on_vm(session, vmuuid, cmd):
    host = Util.get_suitable_vm_ip(session, vmuuid)
    result = Util.execute_ssh(session, host, cmd)
    return result


def get_ps_dict(session, vmuuid):
    cmd = ['docker', 'ps', '--no-trunc=true', '--all=true']
    result = _execute_cmd_on_vm(session, vmuuid, cmd)
    # The ugly part - converting the text table to a dict
    linebyline = result.strip().split('\n')
    columns = []
    for column in linebyline[0].split():
        columns.append({'name': column,
                        'position': linebyline[0].find(column)})
    psresult = []
    for line in linebyline[1:]:
        psentry = {}
        for columnpos in range(0, len(columns)):
            columnstart = columns[columnpos]['position']
            if columnpos + 1 < len(columns):
                nextcolumnstart = columns[columnpos + 1]['position']
            else:
                nextcolumnstart = None
            name = columns[columnpos]['name']
            value = line[columnstart:nextcolumnstart].strip()
            psentry.update({name.lower(): value})
        psresult.append({'entry': psentry})
    return psresult


def get_ps_xml(session, vmuuid):
    result = {'docker_ps': get_ps_dict(session, vmuuid)}
    return Util.converttoxml(result)


def get_stateorversion_dict(session, vmuuid, mode):
    cmd = ['docker', mode]
    result = _execute_cmd_on_vm(session, vmuuid, cmd)
    linebyline = result.strip().split('\n')
    returnarray = []
    for line in linebyline:
        (name, value) = line.split(': ')
        returnarray.append({'property': {'name': name, 'value': value}})
    return returnarray


def get_info_xml(session, vmuuid):
    result = {'docker_info': get_stateorversion_dict(session, vmuuid, 'info')}
    return Util.converttoxml(result)


def get_version_xml(session, vmuuid):
    result = {'docker_version': get_stateorversion_dict(session, vmuuid,
                                                        'version')}
    return Util.converttoxml(result)


def passthrough(session, vmuuid, command):
    cmd = [command]
    result = _execute_cmd_on_vm(session, vmuuid, cmd)
    return result


def monitor_vm(session, vmuuid):
    # ToDo: must make this so much more efficient!
    Util.log("Monitor %s" % vmuuid)
    vmref = ApiHelper.get_vm_ref_by_uuid(session, vmuuid)
    # ApiHelper.update_vm_other_config(
    #    session, vmref, 'docker_version', get_version(session, vmuuid))
    # ToDo: maintain connection to a VM
    # ApiHelper.update_vm_other_config(
    #    session, vmref, 'docker_info', get_info(session, vmuuid))
    ApiHelper.update_vm_other_config(
        session, vmref, 'docker_ps', get_ps_xml(session, vmuuid))


def monitor_host(returninstantly=False):
    # ToDo: must tidy this
    # ToDo: must make this so much more efficient!
    vmuuidstomonitor = []
    passedtime = 10
    session = None
    while True:
        starttime = time.time()
        # Do throttle
        if passedtime < 10:
            time.sleep(10 - passedtime)
        # Make sure that we can talk to XAPI
        vmrecords = None
        try:
            if session == None:
                session = ApiHelper.get_local_api_session()
            vmrecords = ApiHelper.get_vm_records(session)
        except Exception, e:
            if None != session:
                # Something is seriously wrong, let's re-connect to XAPI
                try:
                    session.xenapi.session.__logout()
                except Exception, e:
                    pass
                session = None
            # Try again from scratch
            passedtime = 0
            continue
        # Detect whether there is changed VM states
        hostref = ApiHelper.get_this_host_ref(session)
        for vmref, vmrecord in vmrecords.iteritems():
            if ('other_config' in vmrecord
                    and 'base_template_name' in vmrecord['other_config']
                    and 'CoreOS' in vmrecord['other_config']['base_template_name']
                    and hostref == vmrecord['resident_on']):
                if vmrecord['power_state'] == 'Running':
                    if vmrecord['uuid'] not in vmuuidstomonitor:
                        Util.log("Adding monitor for VM name: %s, UUID: %s"
                                 % (vmrecord['name_label'], vmrecord['uuid']))
                        vmuuidstomonitor.append(vmrecord['uuid'])
                else:
                    if 'docker_ps' in vmrecord['other_config']:
                        Util.log("Removing monitor for VM name: %s, UUID: %s"
                                 % (vmrecord['name_label'], vmrecord['uuid']))
                        session.xenapi.VM.remove_from_other_config(
                            vmref, 'docker_ps')
                        # session.xenapi.VM.remove_from_other_config(vmref,
                        #    'docker_info')
                        # session.xenapi.VM.remove_from_other_config(vmref,
                        #    'docker_version')
                    if vmrecord['uuid'] in vmuuidstomonitor:
                        vmuuidstomonitor.remove(vmrecord['uuid'])
        for vmuuid in vmuuidstomonitor:
            try:
                monitor_vm(session, vmuuid)
            except Exception, e:
                # Ignore single VM failures and move on
                pass
        # Try to idle, if performance allows
        passedtime = time.time() - starttime
        if returninstantly:
            break


def _get_inspect_dict(session, vmuuid, container):
    cmd = ['docker', 'inspect', container]
    result = _execute_cmd_on_vm(session, vmuuid, cmd)
    result = simplejson.loads(result)
    newresult = []
    for key, value in result[0].iteritems():
        newresult.append({'property': {'name': key, 'value': value}})
    return newresult


def get_inspect_xml(session, vmuuid, container):
    result = _get_inspect_dict(session, vmuuid, container)
    return Util.converttoxml({'docker_inspect': result})


def _simplecommand(session, vmuuid, container, command):
    cmd = ['docker', command, container]
    return _execute_cmd_on_vm(session, vmuuid, cmd)


def start(session, vmuuid, container):
    result = _simplecommand(session, vmuuid, container, 'start')
    monitor_vm(session, vmuuid)
    return result


def stop(session, vmuuid, container):
    result = _simplecommand(session, vmuuid, container, 'stop')
    monitor_vm(session, vmuuid)
    return result


def restart(session, vmuuid, container):
    result = _simplecommand(session, vmuuid, container, 'restart')
    monitor_vm(session, vmuuid)
    return result


def pause(session, vmuuid, container):
    result = _simplecommand(session, vmuuid, container, 'pause')
    monitor_vm(session, vmuuid)
    return result


def unpause(session, vmuuid, container):
    result = _simplecommand(session, vmuuid, container, 'unpause')
    monitor_vm(session, vmuuid)
    return result
