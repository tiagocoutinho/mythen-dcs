from __init__ import Const
import h5py
import numpy as np

class MythenPostProcessing(object):
    """
    Class to calculate the sum of images in one scan
    """

    def __init__(self, filename, channel_name):
       """
       :param filename: file name of the nexus file (ffff.h5)
       :param channel_name: mythendcs 1D channel name used in the measurement group
       :return:
       """
        self.file = h5py.File(filename, 'r')
        self.channel_name = channel_name

    def get_channel_data(self, scan_id, channel_name):
        """
        :param scan_id: scan id
        :param channel_name: channel name
        :return: a numpy array or throw an exception if the scan_id or
        channel_name do not exist
        """
        try:
            key_name = '/entry%i/measurement/%s' % (scan_id, channel_name)
            data = list(self.file[key_name])
        except Exception, e:
            msg = 'Wrong scan_id or channel_name. %s' % e
            raise ValueError(msg)
        return data

    def get_mythen_data(self, scan_id):
        """
        :param scan_id: scan id
        :return: a numpy array or throw an exception if the scan_id or
        channel_name do not exist
        """
        return self.get_channel_data(scan_id, self.channel_name)


    def calc_average(self, scan_id):
        """
        :param scan_id: number of the scan
        :return: a numpy array
        """
        data = self.get_mythen_data(scan_id)
        average = np.zeros(len(data[0]))
        for i in data:
            average += i
        average /= len(data)
        return average

    def calc_integration(self, scan_id, roi ):
        """
        :param scan_id: number of the scan
        :param roi: array with low and high pixel [low, high]
        :return: a numpy array with the new integration per image
        """
        data = self.get_mythen_data(scan_id)
        integration = np.zeros(len(data))
        for index, image in enumerate(data):
            integration[index] = sum(image[roi[0]:roi[1]])
        return integration

    def merge_scans(self, scans_id, normalized=True, time_channel_name=None):
        """
        :param scans_id: array with the scans number to merge
        :param normalized: flag to identify if the channel is normalized
        :param time_channel_name: to normalize the data if it need it.
        :return:
        """
        merge = self.get_mythen_data(scans_id[0])
        if not normalized:
            integration_time = self.get_channel_data(scans_id[0],
                                                     time_channel_name)
            merge /= integration_time[0]
        for scan_id in scans_id[1:]:
            data = self.get_mythen_data(scan_id)
            if not normalized:
                integration_time = self.get_channel_data(scans_id[0],
                                                     time_channel_name)
                data /= integration_time[0]
            merge = np.concatenate((merge, data))
        return merge









