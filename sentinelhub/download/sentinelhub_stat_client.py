"""
Download process for Sentinel Hub Stat API
"""
import copy
import os
import concurrent.futures

from .sentinelhub_client import SentinelHubDownloadClient
from ..constants import MimeType
from ..decoding import decode_data as decode_data_function
from ..io_utils import read_data, write_data


class SentinelHubStatDownloadClient(SentinelHubDownloadClient):
    """ A special download client for Sentinel Hub Stat API

    Besides a normal download from Sentinel Hub services it implements an additional process of retrying and caching
    """
    _RETIRABLE_ERRORS = ['EXECUTION_ERROR', 'TIMEOUT']
    _RETRY_NUM = 1

    def _single_download(self, request, _):
        """ Method for downloading a single request
        """
        request.raise_if_invalid()
        if not (request.save_response or request.return_data):
            return None

        request_path, response_path = request.get_storage_paths()

        download_required = self.redownload or response_path is None or not os.path.exists(response_path)
        if download_required:
            response_content = self._execute_download(request)
            stats_response = decode_data_function(response_content, request.data_type)
        else:
            stats_response = read_data(response_path, data_format=request.data_type)

        failed_time_intervals = {}
        for index, stat_info in enumerate(stats_response['data']):
            if self._has_retriable_error(stat_info):
                failed_time_intervals[index] = stat_info['interval']

        n_succeeded_intervals = 0
        if failed_time_intervals:
            retried_responses = self._download_per_interval(request, failed_time_intervals)
            n_succeeded_intervals = sum('error' not in stat_info for stat_info in retried_responses.values())

            stats_response['data'] = [
                retried_responses.get(index, stat_info) for index, stat_info in enumerate(stats_response['data'])
            ]

        if request_path and request.save_response and (self.redownload or not os.path.exists(request_path)):
            request_info = request.get_request_params(include_metadata=True)
            write_data(request_path, request_info, data_format=MimeType.JSON)

        if request.save_response and (download_required or n_succeeded_intervals > 0):
            write_data(response_path, stats_response, data_format=request.data_type)

        if request.return_data:
            return stats_response
        return None

    def _download_per_interval(self, request, time_intervals):
        """ Download statistics per each time interval
        """
        interval_requests = []
        for time_interval in time_intervals.values():
            interval_request = copy.deepcopy(request)
            interval_request.post_values['aggregation']['timeRange'] = time_interval
            interval_requests.append(interval_request)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            stat_info_responses = list(executor.map(self._execute_single_stat_download, interval_requests))

        return {index: stat_info for index, stat_info in zip(time_intervals, stat_info_responses)}

    def _execute_single_stat_download(self, request):
        """ Makes sure a download for a single time interval is retried
        """
        for retry_count in range(self._RETRY_NUM):
            response = self._execute_download(request)
            stat_response = decode_data_function(response, request.data_type)
            stat_info = stat_response['data'][0]

            if not self._has_retriable_error(stat_info) or retry_count == self._RETRY_NUM - 1:
                return stat_info

        raise ValueError('No retries done')

    def _has_retriable_error(self, stat_info):
        """ Checks if a dictionary of Stat API info for a single time interval has an error that can fixed by retrying
        a request
        """
        error_type = stat_info.get('error', {}).get('type')
        return error_type in self._RETIRABLE_ERRORS
