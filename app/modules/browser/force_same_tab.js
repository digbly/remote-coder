// Injected into every page of the streamed browser session.
//
// The panel is a single viewport with no tab bar, so a native "new tab" would
// navigate somewhere the user cannot see. Keep simple navigations in the
// current tab so clicking a link always shows where it leads.
(function () {
  try {
    window.addEventListener(
      'click',
      (event) => {
        const anchor =
          event.target && event.target.closest ? event.target.closest('a[target]') : null
        if (anchor) anchor.target = '_self'
      },
      true,
    )

    const nativeOpen = window.open.bind(window)
    window.open = function (url, name, features) {
      // Popup-style calls (with features, e.g. OAuth login) keep the native
      // behavior so page scripts can still use the returned window; only simple
      // navigations are redirected into the current tab.
      if (url && !features) {
        window.location.href = url
        return null
      }
      return nativeOpen(url, name, features)
    }
  } catch (error) {
    void error
  }
})()
