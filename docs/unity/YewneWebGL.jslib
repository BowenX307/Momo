// 于你 Yewne · WebGL 音频插件(配合 YewneClient.cs 使用)
// ------------------------------------------------------------------
// WebGL 上 Unity 没有本地文件系统,file:// 读不了临时 MP3,
// 所以把 base64 转成 Blob URL,让浏览器自己去取、自己解码。
//
// 用法:把这个文件放进 Assets/Plugins/ 目录(必须是这个目录,Unity 只认这里的 .jslib)。
// 只在 WebGL 构建时生效,其他平台会被忽略,放着不碍事。
// ------------------------------------------------------------------
mergeInto(LibraryManager.library, {

  YewneCreateBlobUrl: function (base64Ptr, mimePtr) {
    var b64   = UTF8ToString(base64Ptr);
    var mime  = UTF8ToString(mimePtr);
    var bin   = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var url  = URL.createObjectURL(new Blob([bytes], { type: mime }));
    var size = lengthBytesUTF8(url) + 1;
    var ptr  = _malloc(size);
    stringToUTF8(url, ptr, size);
    return ptr;
  },

  YewneRevokeBlobUrl: function (urlPtr) {
    URL.revokeObjectURL(UTF8ToString(urlPtr));
  }
});
