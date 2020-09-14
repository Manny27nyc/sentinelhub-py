"""
Module implementing an interface with Sentinel Hub Batch service
"""
from urllib.parse import urlencode

from .config import SHConfig
from .constants import RequestType
from .download.sentinelhub_client import get_auth_json
from .geometry import Geometry, BBox, CRS
from .sentinelhub_request import SentinelHubRequest


class SentinelHubBatch:
    """ An interface class for Sentinel Hub Batch API

    For more info check `Batch API reference <https://docs.sentinel-hub.com/api/latest/reference/#tag/batch_process>`_.
    """
    _REPR_PARAM_NAMES = ['id', 'description', 'bucketName', 'created', 'status', 'userAction', 'valueEstimate']

    def __init__(self, request_id=None, *, request_info=None, config=None):
        """
        :param request_id: A batch request ID
        :type request_id: str or None
        :param request_info: Information about batch request parameters obtained from the service. This parameter can
            be given instead of `request_id`
        :type request_info: dict or None
        :param config: A configuration object
        :type config: SHConfig or None
        """
        if not (request_id or request_info):
            raise ValueError('One of the parameters request_id and request_info has to be given')

        self.request_id = request_id if request_id else request_info['id']
        self.config = config or SHConfig()
        self._request_info = request_info

    def __repr__(self):
        """ A representation that shows the basic parameters of a batch job
        """
        repr_params = {name: self.info[name] for name in self._REPR_PARAM_NAMES if name in self.info}
        repr_params_str = '\n  '.join(f'{name}: {value}' for name, value in repr_params.items())
        return f'{self.__class__.__name__}({{\n  {repr_params_str}\n  ...\n}})'

    @classmethod
    def create(cls, sentinelhub_request, tiling_grid, output=None, bucket_name=None, description=None, config=None):
        """ Create a new batch request

        :param sentinelhub_request: An instance of SentinelHubRequest class containing all request parameters.
            Alternatively, it can also be just a payload dictionary for Processing API request
        :type sentinelhub_request: SentinelHubRequest or dict
        :param tiling_grid: A dictionary with tiling grid parameters. It can be build with `tiling_grid` method
        :type tiling_grid: dict
        :param output: A dictionary with output parameters. It can be build with `output` method. Alternatively, one
            can set `bucket_name` parameter instead.
        :type output: dict or None
        :param bucket_name: A name of an s3 bucket where to save data. Alternatively, one can set `output` parameter
            to specify more output parameters.
        :type bucket_name: str or None
        :param description: A description of a batch request
        :type description: str or None
        :param config: A configuration object
        :type config: SHConfig or None
        """
        if isinstance(sentinelhub_request, SentinelHubRequest):
            sentinelhub_request = sentinelhub_request.download_list[0].post_values
        if not isinstance(sentinelhub_request, dict):
            raise ValueError('Parameter sentinelhub_request should be an instance of SentinelHubRequest or a '
                             'dictionary of request payload')

        payload = {
            'processRequest': sentinelhub_request,
            'tilingGrid': tiling_grid,
            'output': output,
            'bucketName': bucket_name,
            'description': description
        }
        payload = _remove_undefined_params(payload)

        url = cls._get_process_url(config)
        request_info = get_auth_json(url, post_values=payload)
        return cls(request_info=request_info, config=config)

    @staticmethod
    def tiling_grid(grid_id, resolution, buffer=None, **kwargs):
        """ A helper method to build a dictionary with tiling grid parameters

        :param grid_id: An ID of a tiling grid
        :type grid_id: int
        :param resolution: A grid resolution
        :type resolution: float or int
        :param buffer: Optionally, a buffer around each tile can be defined. It can be defined with a tuple of integers
            `(buffer_x, buffer_y)`, which specifies a number of buffer pixels in horizontal and vertical directions.
        :type buffer: (int, int) or None
        :param kwargs: Any other arguments to be added to a dictionary of parameters
        :return: A dictionary with parameters
        :rtype: dict
        """
        payload = {
            'id': grid_id,
            'resolution': resolution,
            **kwargs
        }
        if buffer:
            payload = {
                **payload,
                'bufferX': buffer[0],
                'bufferY': buffer[1]
            }
        return payload

    @staticmethod
    def output(*, default_tile_path=None, cog_output=None, cog_parameters=None, create_collection=None,
               collection_id=None, responses=None, **kwargs):
        """ A helper method to build a dictionary with tiling grid parameters

        :param default_tile_path: A path or a template on an s3 bucket where to store results. More info at Batch API
            documentation
        :type default_tile_path: str or None
        :param cog_output: A flag specifying if outputs should be written in COGs (cloud-optimized GeoTIFFs )or
            normal GeoTIFFs
        :type cog_output: bool or None
        :param cog_parameters: A dictionary specifying COG creation parameters
        :type cog_parameters: dict or None
        :param create_collection: If True the results will be written in COGs and a batch collection will be created
        :type create_collection: bool or None
        :param collection_id: If True results will be added to an existing collection
        :type collection_id: str or None
        :param responses: Specification of path template for individual outputs/responses
        :type responses: list or None
        :param kwargs: Any other arguments to be added to a dictionary of parameters
        :return: A dictionary of output parameters
        :rtype: dict
        """
        return _remove_undefined_params({
            'defaultTilePath': default_tile_path,
            'cogOutput': cog_output,
            'cogParameters': cog_parameters,
            'createCollection': create_collection,
            'collectionId': collection_id,
            'responses': responses,
            **kwargs
        })

    @staticmethod
    def iter_tiling_grids(search=None, sort=None, config=None, **kwargs):
        """ An iterator over tiling grids

        :param search: A search parameter
        :type search: str
        :param sort: A sort parameter
        :type sort: str
        :param config: A configuration object
        :type config: SHConfig
        :param kwargs: Any other request query parameters
        :return: An iterator over tiling grid definitions
        :rtype: Iterator[dict]
        """
        url = SentinelHubBatch._get_tiling_grids_url(config)
        params = _remove_undefined_params({
            'search': search,
            'sort': sort,
            **kwargs
        })
        return _iter_pages(url, **params)

    @staticmethod
    def get_tiling_grid(grid_id, config=None):
        """ Provides a single tiling grid

        :param grid_id: An ID of a requested tiling grid
        :type grid_id: str or int
        :param config: A configuration object
        :type config: SHConfig
        :return: A tiling grid definition
        :rtype: dict
        """
        url = f'{SentinelHubBatch._get_tiling_grids_url(config)}/{grid_id}'
        return get_auth_json(url)

    @property
    def info(self):
        """ A dictionary with a Batch request information. It loads a new dictionary only if one doesn't exist yet.

        :return: Batch request info
        :rtype: dict
        """
        if self._request_info is None:
            self.update_info()
        return self._request_info

    def update_info(self):
        """ Updates information about a batch request

        :return: Batch request info
        :rtype: dict
        """
        url = self._get_process_url(self.config, request_id=self.request_id)
        self._request_info = get_auth_json(url)

    @property
    def evalscript(self):
        """ Provides an evalscript used by a batch request

        :return: An evalscript
        :rtype: str
        """
        return self.info['processRequest']['evalscript']

    @property
    def geometry(self):
        """ Provides a geometry used by a batch request

        :return: Either a Geometry or a BBox object, which also contains a CRS
        :rtype: Geometry or BBox
        """
        bounds_definition = self.info['processRequest']['input']['bounds']
        crs = CRS(bounds_definition['properties']['crs'].rsplit('/', 1)[-1])

        if 'bbox' in bounds_definition:
            return BBox(bounds_definition['bbox'], crs)
        return Geometry(bounds_definition['geometry'], crs)

    @staticmethod
    def iter_requests(search=None, sort=None, user_id=None, config=None, **kwargs):
        """ Iterate existing batch requests

        :param search: Filter requests by a search query
        :type search: str or None
        :param sort: Sort obtained batch requests in a specific order
        :type sort: str or None
        :param user_id: Filter requests by a user id who defined a request
        :type user_id: str or None
        :param config: A configuration object
        :type config: SHConfig or None
        :param kwargs: Any additional parameters to include in a request query
        :return: An iterator over existing batch requests
        :rtype: Iterator[SentinelHubBatch]
        """
        url = SentinelHubBatch._get_process_url(config)
        params = _remove_undefined_params({
            'search': search,
            'sort': sort,
            'userid': user_id,
            **kwargs
        })
        for request_info in _iter_pages(url, **params):
            yield SentinelHubBatch(request_info=request_info, config=config)

    @staticmethod
    def get_latest_request(config=None):
        """ Provides a batch request that has been created the latest
        """
        # This should be improved once sort parameter will be supported
        batch_requests = list(SentinelHubBatch.iter_requests(config=config))
        return max(*batch_requests, key=lambda request: request.info['created'])

    def start_analysis(self):
        """ Starts analysis of a batch job request
        """
        self._call_job('analyse')

    def start_job(self):
        """ Starts running a batch job
        """
        self._call_job('start')

    def cancel_job(self):
        """ Cancels a batch job
        """
        self._call_job('cancel')

    def restart_job(self):
        """ Restarts only those parts of a job that failed
        """
        self._call_job('restartpartial')

    def iter_tiles(self, status=None, **kwargs):
        """ Iterate over info about batch request tiles

        :param status: A filter to obtain only tiles with a certain status
        :type status: str or None
        :param kwargs: Any additional parameters to include in a request query
        :return: An iterator over information about each tile
        :rtype: Iterator[dict]
        """
        url = self._get_tiles_url()
        params = _remove_undefined_params({
            'status': status,
            **kwargs
        })
        return _iter_pages(url, **params)

    def get_tile(self, tile_id):
        """ Provides information about a single batch request tile

        :param tile_id: An ID of a tile
        :type tile_id: int or None
        :return: Information about a tile
        :rtype: dict
        """
        url = self._get_tiles_url(tile_id=tile_id)
        return get_auth_json(url)

    def reprocess_tile(self, tile_id):
        """ Reprocess a single failed tile

        :param tile_id: An ID of a tile
        :type tile_id: int or None
        """
        self._call_job(f'tiles/{tile_id}/restart')

    def _call_job(self, endpoint_name):
        """ Makes a POST request to the service that triggers a processing job
        """
        process_url = self._get_process_url(request_id=self.request_id, config=self.config)
        url = f'{process_url}/{endpoint_name}'
        get_auth_json(url, request_type=RequestType.POST)

    def _get_tiles_url(self, tile_id=None):
        """ Creates an URL for tiles endpoint
        """
        process_url = self._get_process_url(config=self.config, request_id=self.request_id)
        url = f'{process_url}/tiles'
        if tile_id:
            return f'{url}/{tile_id}'
        return url

    @staticmethod
    def _get_process_url(config, request_id=None):
        """ Creates an URL for process endpoint
        """
        url = f'{SentinelHubBatch._get_batch_url(config=config)}/process'
        if request_id:
            return f'{url}/{request_id}'
        return url

    @staticmethod
    def _get_tiling_grids_url(config):
        """ Creates an URL for tiling grids endpoint
        """
        return f'{SentinelHubBatch._get_batch_url(config=config)}/tilinggrids'

    @staticmethod
    def _get_batch_url(config=None):
        """ Creates an URL of the base batch service
        """
        config = config or SHConfig()
        return f'{config.sh_base_url}/api/v1/batch'


def _remove_undefined_params(payload):
    """ Takes a dictionary with a payload and removes parameter which value is None
    """
    return {name: value for name, value in payload.items() if value is not None}


def _iter_pages(service_url, **params):
    """ Iterates over pages of items
    """
    token = None

    while True:
        if token is not None:
            params['viewtoken'] = token

        url = f'{service_url}?{urlencode(params)}'
        results = get_auth_json(url)

        for item in results['member']:
            yield item

        token = results['view'].get('nextToken')
        if token is None:
            break
