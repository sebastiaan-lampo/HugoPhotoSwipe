# -*- coding: utf-8 -*-

"""Class for albums of photos

The Album class has all the methods needed for updating albums, creating the 
album markdown, etc.

Author: Gertjan van den Burg
License: GPL v3.

"""

from __future__ import print_function

import logging
import os
import shutil
import yaml
from PIL import UnidentifiedImageError

from tqdm import tqdm

from .conf import settings
from .photo import Photo
from .utils import yaml_field_to_file, modtime, question_yes_no, mkdirs

logger = logging.getLogger(__name__)


class Album(object):
    def __init__(
            self,
            album_dir=None,
            title=None,
            album_date=None,
            properties=None,
            copyright=None,
            coverimage=None,
            creation_time=None,
            modification_time=None,
            photos=None,
            hashes=None,
    ):

        self._album_dir = album_dir
        self._album_file = None
        if not self._album_dir is None:
            self._album_file = os.path.join(album_dir, settings.album_file)

        self.title = title
        self.album_date = album_date
        self.properties = properties
        self.copyright = copyright
        self.coverimage = coverimage
        self.creation_time = creation_time
        self.modification_time = modification_time
        self.photos = [] if photos is None else photos
        self.hashes = [] if hashes is None else hashes

    ##############
    #            #
    # Properties #
    #            #
    ##############

    @property
    def name(self):
        """ Name of the album """
        base_album_dir = os.path.basename(self._album_dir)
        return base_album_dir

    @property
    def names_unique(self):
        return len(set([p.name for p in self.photos])) == len(self.photos)

    @property
    def markdown_file(self):
        """ Path of the markdown file """
        md_dir = os.path.realpath(settings.markdown_dir)
        mkdirs(md_dir)
        return os.path.join(md_dir, self.name + ".md")

    @property
    def output_dir(self):
        """ Base dir for the processed images """
        pth = os.path.realpath(settings.output_dir)
        return os.path.join(pth, self.name)

    @property
    def markdown_dir(self):
        return os.path.join(os.path.realpath(settings.markdown_dir), self.name)

    ################
    #              #
    # User methods #
    #              #
    ################

    def clean(self):
        """ Clean up the processed images and the markdown file

        Ask the user for confirmation and only remove if it exists
        """
        have_md = os.path.exists(self.markdown_file)
        have_md_dir = os.path.exists(self.markdown_dir)
        have_out = os.path.exists(self.output_dir)

        q = ["Going to remove: "]
        if have_md:
            q.append("  - (File) {}".format(self.markdown_file))
        if have_md_dir:
            q.append("  - (Dir) {}".format(self.markdown_dir))
        if have_out:
            q.append("  - (Dir) {}".format(self.output_dir))
        q.append("Is this okay?")
        if True not in [have_md, have_md_dir, have_out]:
            return
        if not question_yes_no("\n".join(q)):
            return

        if have_md:
            logging.info(
                "[%s] Removing markdown file: %s"
                % (self.name, self.markdown_file)
            )
            os.unlink(self.markdown_file)
        if have_md_dir:
            logging.info(f"[{self.name}] Removing markdown directory: {self.markdown_dir}")
            shutil.rmtree(self.markdown_dir)
        if have_out:
            logging.info(
                "[%s] Removing images directory: %s" % (self.name, self.output_dir)
            )
            shutil.rmtree(self.output_dir)

    def create_markdown_bundle(self):
        """ Create a branch bundle of markdown files, one per photo with an _index.md

            Output is generated in a sub folder with the *album_name*. Each photo markdown file
            will have the photo properties in front matter and the shortcode in content.
        """
        album_md_template = ("---",
                             "title: {title}",
                             "date: {date}",
                             "{album_properties}",
                             "---",
                             )
        album_md_template = "\n".join(album_md_template)
        photo_md_template = ("---",
                             "{photo_properties}",
                             "{exif_iptc}"
                             "---",
                             "",
                             "{shortcode}"
                             )
        photo_md_template = "\n".join(photo_md_template)

        if self.properties:
            album_properties = yaml.dump(self.properties, default_flow_style=False)
        else:
            album_properties = ""
        logging.debug('album_properties text:\n\t'.format(album_properties))

        album_dir = os.path.join(os.path.realpath(settings.markdown_dir), self.name)
        mkdirs(album_dir)

        with open(os.path.join(album_dir, "_index.md"), "w") as f:
            logging.debug('Writing album md file to {}'.format(os.path.join(album_dir, "_index.md")))
            f.write(album_md_template.format(title=self.title,
                                             cover=self.coverimage,
                                             date=self.album_date,
                                             album_properties=album_properties))
        for photo in self.photos:
            logging.info('Writing photo md file to {}'.format(os.path.join(album_dir, photo.clean_name) + ".md"))

            _ = {}
            if settings.exif.get('dump', False):
                _.update(photo.exif)
            if settings.iptc.get('dump', False):
                _.update(photo.iptc)
            exif_iptc = yaml.dump(_, default_flow_style=False) if _ and len(_) > 0 else ""

            with open(os.path.join(album_dir, photo.clean_name) + ".md", "w") as f:
                try:
                    photo_properties = yaml.dump(photo.properties, default_flow_style=False)
                except AttributeError:
                    photo_properties = ""

                f.write(photo_md_template.format(
                    exif_iptc=exif_iptc,
                    shortcode=photo.shortcode,
                    photo_properties=photo_properties,
                ))

    def create_markdown(self):
        """ Create the markdown file, always overwrite existing """
        # Create the header for Hugo
        coverpath = ""
        if not self.coverimage is None:
            coverpath = (
                    settings.url_prefix
                    + self.cover_path[len(settings.output_dir):]
            )
            # path should always be unix style for Hugo frontmatter
            coverpath = coverpath.replace("\\", "/")

        if self.properties is None:
            proptxt = [""]
        else:
            proptxt = [
                '%s = """%s"""' % (k, v) for k, v in self.properties.items()
            ]

        txt = [
            "+++",
            'title = "%s"' % self.title,
            'date = "%s"'
            % ("" if self.album_date is None else self.album_date),
            "%s" % ("\n".join(proptxt)),
            'cover = "%s"' % coverpath,
            "+++",
            "",
            "{{< wrap >}}",  # needed to avoid <p> tags from hugo
        ]
        for photo in self.photos:
            txt.append(photo.shortcode)
            txt.append("")

        txt.append("{{< /wrap >}}")
        with open(self.markdown_file, "w") as fid:
            fid.write("\n".join(txt))
        print("Written markdown file: %s" % self.markdown_file)

    def dump(self):
        """ Save the album configuration to a YAML file """
        if self._album_file is None:
            raise ValueError("Album file is not defined.")

        # create a backup first
        self._backup()

        # now overwrite the existing file
        with open(self._album_file, "w") as fid:
            fid.write("---\n")
            yaml_field_to_file(fid, self.title, "title")
            yaml_field_to_file(
                fid, self.album_date, "album_date", force_string=True
            )
            yaml_field_to_file(fid, None, "properties")
            if self.properties:
                for name, field in sorted(self.properties.items()):
                    yaml_field_to_file(fid, field, name, indent="  ")
            yaml_field_to_file(fid, self.copyright, "copyright")
            yaml_field_to_file(fid, self.coverimage, "coverimage")
            yaml_field_to_file(
                fid, self.creation_time, "creation_time", force_string=True
            )
            yaml_field_to_file(
                fid, modtime(), "modification_time", force_string=True
            )

            fid.write("\n")
            fid.write("photos:")
            for photo in self.photos:
                fid.write("\n")
                yaml_field_to_file(fid, photo.filename, "file", indent="- ")
                yaml_field_to_file(fid, photo.name, "name", indent="  ")
                yaml_field_to_file(fid, photo.alt, "alt", indent="  ")
                yaml_field_to_file(
                    fid, photo.clean_caption, "caption", indent="  "
                )

            fid.write("\n")
            fid.write("hashes:")
            for photo in self.photos:
                fid.write("\n")
                yaml_field_to_file(fid, photo.filename, "file", indent="- ")
                yaml_field_to_file(fid, hash(photo), "hash", indent="  ")
        print("Updated album file: %s" % self._album_file)

    @classmethod
    def load(cls, album_dir):
        """ Load an Album class from an album directory """
        album_file = os.path.join(album_dir, settings.album_file)
        data = {"album_dir": album_dir}
        if os.path.exists(album_file):
            with open(album_file, "r") as fid:
                data.update(yaml.safe_load(fid))
        else:
            logging.info("Skipping non-album directory: %s" % album_dir)
            return None
        album = cls(**data)
        album.cover_path = os.path.join(
            settings.output_dir, album.name, settings.cover_filename
        )

        all_photos = []
        for p in album.photos:
            photo_path = os.path.join(album_dir, settings.photo_dir, p["file"])
            caption = "" if p["caption"] is None else p["caption"].strip()
            try:
                photo = Photo(
                    album_name=album.name,
                    original_path=photo_path,
                    name=p["name"],
                    alt=p["alt"],
                    caption=caption,
                    copyright=album.copyright,
                )
                all_photos.append(photo)
            except PermissionError:
                pass
            # except UnidentifiedImageError:
            #     pass

        album.photos = []
        for photo in all_photos:
            if photo.name is None:
                print("No name defined for photo %r. Using filename." % photo)
                continue
            album.photos.append(photo)
        return album

    def update(self):
        """ Update the processed images and the markdown file """
        # logger.setLevel(logging.DEBUG)
        logger.info(f'Processing update of album. {self.name}')
        if not self.names_unique:
            logging.warning("Photo names for this album aren't unique. Not processing.")
            return
        # Make sure the list of photos from the yaml is up to date with
        # the photos in the directory, simply add all the new photos to
        # self.photos
        photo_files = [p.filename for p in self.photos]
        photo_dir = os.path.join(self._album_dir, settings.photo_dir)
        _, _, candidate_files = next(os.walk(photo_dir))
        missing = [f for f in candidate_files if f not in photo_files]
        missing.sort()
        for f in missing:
            logger.info(f'\tLoading photo file: {f}')
            try:
                pho = Photo(
                    album_name=self.name,
                    original_path=os.path.join(photo_dir, f),
                    name=f,
                    copyright=self.copyright,
                )
                _ = pho.original_image  # Force loading the image to test if it's real
                # del _
                # logger.debug(f'Object situation: {gc.get_objects()}')
                # gc.collect()
                self.photos.append(pho)
            except PermissionError:
                pass  # Most likely a directory instead of a file.
            except UnidentifiedImageError:
                pass  # Not a photo file
        logger.info(
            "[%s] Found %i photos from yaml and photos dir"
            % (self.name, len(self.photos))
        )

        # Remove the photos whose files don't exist anymore
        to_remove = []
        for photo in self.photos:
            if not os.path.exists(photo.original_path):
                to_remove.append(photo)
        for photo in to_remove:
            self.photos.remove(photo)
        logger.info(
            "[%s] Removed %i photos that have been deleted."
            % (self.name, len(to_remove))
        )

        # set the coverpath to the photo that should be the cover image
        for photo in self.photos:
            if photo.filename == self.coverimage:
                photo.cover_path = self.cover_path
            else:
                photo.cover_path = None

        # Iterate over all photos and create new resizes if they don't
        # exist yet, or the hash in self.hashes is different than the hash of
        # the current file on disk.
        photo_hashes = {}
        for photo in self.photos:
            hsh = next(
                (
                    h["hash"]
                    for h in self.hashes
                    if h["file"] == photo.filename
                ),
                None,
            )
            photo_hashes[photo] = hsh

        to_process = []
        for p in self.photos:
            if not (p.has_sizes() and (hash(p) == photo_hashes[p])):
                to_process.append(p)

        logging.info(
            "[%s] There are %i photos to process."
            % (self.name, len(to_process))
        )
        if to_process:
            iterator = (
                iter(to_process)
                if settings.verbose
                else tqdm(to_process, desc="Progress")
            )
            for photo in iterator:
                photo.create_sizes()
                del photo.original_image

        # Overwrite the markdown file
        logging.info("[%s] Writing markdown file." % self.name)
        if settings.generate_branch_bundle:
            self.create_markdown_bundle()
        else:
            self.create_markdown()

        # Overwrite the yaml file of the album
        logging.info("[%s] Saving album yaml." % self.name)
        self.dump()

    ####################
    #                  #
    # Internal methods #
    #                  #
    ####################

    def _backup(self):
        """ Create a backup of the album file if it exists """
        if not os.path.exists(self._album_file):
            return
        backupfile = self._album_file + ".bak"
        shutil.copy2(self._album_file, backupfile)
