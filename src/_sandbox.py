# -*- coding: utf-8 -*-

import math
import datetime as dt
import tzlocal
import pyyoutube as pyt

import youtube

"""File Information
@file_name: _sandbox.py
@author: Dylan "dyl-m" Monfret
To test things / backup functions.
"""

playlist_target = ''
re_listening = 'PLOMUdQFdS-XP8fi89uBQ5P01DN_9tGJHu'
legacy = 'PLOMUdQFdS-XNY3dxJ3od6dvTVko91Q9PF'
date_format = '%Y-%m-%dT%H:%M:%S%z'
NOW = dt.datetime.now(tz=tzlocal.get_localzone())


def fill_release_radar(service: pyt.Client, target_playlist: str, re_listening_id: str = "0", legacy_id: str = "0"):
    """
    :param service:
    :param target_playlist:
    :param re_listening_id:
    :param legacy_id:
    :return:
    """
    week_ago = NOW - dt.timedelta(weeks=1)

    # Compute how much videos are necessary to fill the target playlist (up to 30 additions)
    n_add = 30 - len(service.playlistItems.list(part=['snippet'], max_results=30, playlist_id=target_playlist).items)

    if n_add == 0:  # Release Radar has too much content already
        print("No addition on Release Radar")

    else:
        n_add_rel, n_add_leg = math.ceil(n_add / 2), math.floor(n_add / 2)  # Initial addition values

        vid_rel_raw = my_service.playlistItems.list(part=['snippet', 'contentDetails'],
                                                    playlist_id=re_listening,
                                                    max_results=n_add_rel).items

        vid_rel = [item for item in vid_rel_raw if item['add_date'] < week_ago]




if __name__ == '__main__':
    # import pprint as pp
    #
    my_service = youtube.create_service_local(log=False)
    #
    # request = my_service.playlistItems.list(part=['snippet', 'contentDetails'],
    #                                         playlist_id=re_listening,
    #                                         max_results=30).items
    #
    # p_items = [{'video_id': item.contentDetails.videoId,
    #             'add_date': dt.datetime.strptime(item.snippet.publishedAt, date_format),
    #             'item_id': item.id} for item in request]
    #
    # p_items = [item for item in p_items if item['add_date'] < A_WEEK_AGO]
    #
    # pp.pprint(p_items)

    fill_release_radar(service=my_service, target_playlist=legacy)

    # print(math.ceil(3 / 2))
