import json
import sys
from collections import Counter
from datetime import datetime
import requests
from config import vk_access_token, vk_user_id, ya_token


class VK:
    base_url = 'https://api.vk.com/method/'

    def _make_url(self, uri):
        return self.base_url+uri

    def __init__(self, access_token, current_user_id, version='5.131'):
        self.version = version
        self.token = access_token
        self.current_user_id = current_user_id
        self.params = {'access_token': self.token, 'v': self.version}

    def users_info(self, user_id):
        params = {'user_ids': user_id}
        response = requests.get(self._make_url('users.get'), params={**self.params, **params})
        return response.json()['response']

    def albums_count(self, user_id):
        params = {'user_id': user_id}
        response = requests.get(self._make_url('photos.getAlbumsCount'), params={**self.params, **params})
        return response.json()['response']

    def albums(self, owner_id):
        params = {'owner_id': owner_id, 'need_system': '1'}
        response = requests.get(self._make_url('photos.getAlbums'), params={**self.params, **params})
        return response.json()['response']

    def photos(self, owner_id, album_id, count='5'):
        params = {'owner_id': owner_id, 'album_id': album_id, 'extended': '1', 'rev': '0', 'count': count}
        response = requests.get(self._make_url('photos.get'), params={**self.params, **params})
        return response.json()['response']


class YaUploader:
    def __init__(self, token: str):
        self.base_host = 'https://cloud-api.yandex.net:443/'
        self.base_headers = {
            'Content-Type': 'application/json',
            'Authorization': f'OAuth {token}'}
        self.successfully_count = 0
        self.error_count = 0

    def _create_folder(self, upload_folder):
        url = self.base_host + 'v1/disk/resources'
        params = {'path': upload_folder}
        response = requests.get(url, params=params, headers=self.base_headers)
        if response.status_code != 200:
            response = requests.put(url, params=params, headers=self.base_headers)
            if response.status_code != 201:
                return dict(status_code=response.status_code, reason=response.reason)
        return response

    def upload(self, url_photo: str, yandex_path: str):
        params = {'url': url_photo, 'path': yandex_path}
        url = self.base_host + 'v1/disk/resources/upload/'
        response = requests.post(url, params=params, headers=self.base_headers)
        return dict(status_code=response.status_code, reason=response.reason)

    def upload_files_list_url(self, photos, upload_folder):
        self.successfully_count = 0
        self.error_count = 0

        r_list = list()
        f = open('log.txt', 'at')

        result = self._create_folder(upload_folder)
        if result.status_code > 202:
            message = f'Upload error. Code {result["status_code"]}: {result["reason"]}'
            print(message)
            f.write(message)
            f.close()
            return

        count = 0
        total = len(photos)
        for p in photos:
            count += 1
            print(f'Copying file: {p["file_name"]}...  ({int(count/total*100)}%)')
            result = self.upload(p['url_photo'], '/' + upload_folder + '/' + p['file_name'])
            if result['status_code'] != 202:
                self.error_count += 1
                message = f'File "{p["file_name"]}" upload error. Code {result["status_code"]}: {result["reason"]}'
                print(f'{datetime.today()}: {message}\n')
                f.write(message)
            else:
                self.successfully_count += 1
                print('Done')
                f.write(f'{datetime.today()}: File "{p["file_name"]}" uploaded successfully\n')
                r_list.append({'file_name': p['file_name'], 'size': p['size']})

        f.close()

        j = json.dumps(r_list, indent=4)
        with open('result.json', 'wt') as r:
            r.write(j+'\n')


class Dialogue:
    def __init__(self, vk):
        self.vk = vk
        self.selected_user_id = ''
        self.selected_album_id = ''
        self.selected_album_size = 0
        self.selected_count_upload_photos = 0
        self.upload_folder = ''

    def open_dialogue(self):
        return self._input_user_id()

    def _input_user_id(self):
        while True:
            command = input('Input user id or "exit" to cancel: ')
            if command.lower() == 'exit':
                return False
            elif command.isdigit():
                info = vk.users_info(int(command))
                if len(info) == 0:
                    continue
                print(f"User selected is {info[0]['first_name']} {info[0]['last_name']}")
                self.selected_user_id = int(command)
                if self._input_album_id():
                    return True

    def _input_album_id(self):
        print('Available albums:')
        albums = self.vk.albums(self.selected_user_id)
        albums_count = 0
        for album in albums['items']:
            albums_count += 1
            # print(f"{albums_count}. Number of photos: {album['size']}. Album title: {album['title']} {album['id']}")
            print(f"{albums_count}. Number of photos: {album['size']}. Album title: {album['title']}")

        while True:
            command = input(f'Enter the album number from 1 to {albums_count} or "exit" to cancel: ')
            if command.lower() == 'exit':
                return False
            elif command.isdigit() and 1 <= int(command) <= albums_count:
                self.selected_album_id = albums['items'][int(command) - 1]['id']
                self.selected_album_size = albums['items'][int(command) - 1]['size']
                if self._input_photos_count():
                    return True

    def _input_photos_count(self):
        if self.selected_album_size == 0:
            print("This album hasn't got a photos")
            return False

        while True:
            command = input(f'Enter the count of photos from 1 to {self.selected_album_size}'
                            f' or "all" for all photos or "exit" to cancel: ')
            if command.lower() == 'exit':
                return False
            elif command.lower() == 'all':
                self.selected_count_upload_photos = int(self.selected_album_size)
                return True
            elif command.isdigit() and 1 <= int(command) <= self.selected_album_size or command.lower() == 'all':
                self.selected_count_upload_photos = int(command)
                return True

    def input_upload_folder(self):
        while True:
            command = input('Input name of the folder to upload or "exit" to cancel: ')
            if command.lower() == 'exit':
                return False
            elif command != '':
                self.upload_folder = command
                return True


class Images:
    def __init__(self, vk, d):
        photos = vk.photos(d.selected_user_id, d.selected_album_id, d.selected_count_upload_photos)
        count = photos['count']
        photos = list({'likes': p['likes']['count'],
                       'date': datetime.fromtimestamp(p['date']).strftime('%Y%m%d_%H%M%S'),
                       'url_photo': p['sizes'][-1]['url'],
                       'size': p['sizes'][-1]['type']} for p in photos['items'])

        doubles_likes = dict(Counter([p['likes'] for p in photos]))
        doubles_likes = list(key for key, value in doubles_likes.items() if value > 1)

        for p in photos:
            if p['likes'] in doubles_likes:
                p['file_name'] = str(p['likes']) + '_' + p['date'] + '.jpg'
            else:
                p['file_name'] = str(p['likes']) + '.jpg'

        self.count = count
        self.photos = photos

    def print_info(self):
        print()
        print(f'А total of {d.selected_count_upload_photos} photos were received for copying')


if __name__ == '__main__':
    vk = VK(vk_access_token, vk_user_id)
    info = vk.users_info(vk_user_id)
    if len(info) > 0:
        print(f"Hello, {info[0]['first_name']} {info[0]['last_name']}!")

    d = Dialogue(vk)
    if not d.open_dialogue():
        sys.exit(0)

    images = Images(vk, d)
    images.print_info()

    if not d.input_upload_folder():
        sys.exit(0)

    uploader = YaUploader(ya_token)
    uploader.upload_files_list_url(images.photos, d.upload_folder)

    print()
    print('Copying completed')
    print('Successfully:', uploader.successfully_count)
    print('Error:', uploader.error_count)