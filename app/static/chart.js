(function () {
  function Chart(target, config) {
    this.config = config;
    var canvas = target && target.getContext ? target : null;
    if (!canvas) return;
    var context = canvas.getContext("2d");
    if (!context) return;
    var labels = (config.data && config.data.labels) || [];
    context.fillStyle = "#1f6f4a";
    labels.forEach(function (_label, index) {
      context.fillRect(12 + index * 48, 30, 28, 40);
    });
    context.fillStyle = "#1b1b1b";
    context.fillText(labels.join(" / "), 12, 18);
  }
  window.Chart = Chart;
})();
