#!/usr/sbin/python
import pytest

import common
from common import client, core_api, csi_pv, pod, pvc  # NOQA
from common import Gi, DEFAULT_VOLUME_SIZE, VOLUME_RWTEST_SIZE
from common import create_and_wait_pod, create_pvc_spec, delete_and_wait_pod
from common import generate_random_data, read_volume_data, write_volume_data

# Using a StorageClass because GKE is using the default StorageClass if not
# specified. Volumes are still being manually created and not provisioned.
CSI_PV_TEST_STORAGE_NAME = 'longhorn-csi-pv-test'


def create_pv_storage(api, cli, pv, claim, base_image):
    """
    Manually create a new PV and PVC for testing.
    """
    cli.create_volume(
        name=pv['metadata']['name'], size=pv['spec']['capacity']['storage'],
        numberOfReplicas=int(pv['spec']['csi']['volumeAttributes']
                             ['numberOfReplicas']), baseImage=base_image)
    common.wait_for_volume_detached(cli, pv['metadata']['name'])

    api.create_persistent_volume(pv)
    api.create_namespaced_persistent_volume_claim(
        body=claim,
        namespace='default')


def update_storageclass_references(name, pv, claim):
    """
    Rename all references to a StorageClass to a specified name.
    """
    pv['spec']['storageClassName'] = name
    claim['spec']['storageClassName'] = name


@pytest.mark.coretest   # NOQA
@pytest.mark.csi  # NOQA
def test_csi_mount(client, core_api, csi_pv, pvc, pod): # NOQA
    """
    Test that a statically defined CSI volume can be created, mounted,
    unmounted, and deleted properly on the Kubernetes cluster.

    Fixtures are torn down here in reverse order that they are specified as a
    parameter. Take caution when reordering test fixtures.
    """
    volume_size = DEFAULT_VOLUME_SIZE * Gi
    csi_mount_test(client, core_api,
                   csi_pv, pvc, pod, volume_size)


def csi_mount_test(client, core_api, csi_pv, pvc, pod,  # NOQA
                   volume_size, base_image=""): # NOQA
    pod_name = 'csi-mount-test'
    pod['metadata']['name'] = pod_name
    pod['spec']['volumes'] = [
        create_pvc_spec(pvc['metadata']['name'])
    ]
    pvc['spec']['volumeName'] = csi_pv['metadata']['name']
    update_storageclass_references(CSI_PV_TEST_STORAGE_NAME, csi_pv, pvc)

    create_pv_storage(core_api, client, csi_pv, pvc, base_image)
    create_and_wait_pod(core_api, pod)

    volumes = client.list_volume()
    assert len(volumes) == 1
    assert volumes[0]["name"] == csi_pv['metadata']['name']
    assert volumes[0]["size"] == str(volume_size)
    assert volumes[0]["numberOfReplicas"] == \
        int(csi_pv['spec']['csi']['volumeAttributes']["numberOfReplicas"])
    assert volumes[0]["state"] == "attached"
    assert volumes[0]["baseImage"] == base_image


@pytest.mark.csi  # NOQA
def test_csi_io(client, core_api, csi_pv, pvc, pod):  # NOQA
    """
    Test that input and output on a statically defined CSI volume works as
    expected.

    Fixtures are torn down here in reverse order that they are specified as a
    parameter. Take caution when reordering test fixtures.
    """
    csi_io_test(client, core_api, csi_pv, pvc, pod)


def csi_io_test(client, core_api, csi_pv, pvc, pod, base_image=""):  # NOQA
    pod_name = 'csi-io-test'
    pod['metadata']['name'] = pod_name
    pod['spec']['volumes'] = [
        create_pvc_spec(pvc['metadata']['name'])
    ]
    pvc['spec']['volumeName'] = csi_pv['metadata']['name']
    update_storageclass_references(CSI_PV_TEST_STORAGE_NAME, csi_pv, pvc)
    test_data = generate_random_data(VOLUME_RWTEST_SIZE)

    create_pv_storage(core_api, client, csi_pv, pvc, base_image)
    create_and_wait_pod(core_api, pod)

    write_volume_data(core_api, pod_name, test_data)
    delete_and_wait_pod(core_api, pod_name)
    common.wait_for_volume_detached(client, csi_pv['metadata']['name'])

    pod_name = 'csi-io-test-2'
    pod['metadata']['name'] = pod_name
    create_and_wait_pod(core_api, pod)

    resp = read_volume_data(core_api, pod_name)

    assert resp == test_data
