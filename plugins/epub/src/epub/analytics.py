import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["bpp"] = df["bpp"].astype(float)
    df["pixels"] = df["size"].apply(lambda x: eval(x)[0] * eval(x)[1] if isinstance(x, str) else x[0] * x[1])
    df["width"] = df["size"].apply(lambda x: eval(x)[0] if isinstance(x, str) else x[0])
    df["height"] = df["size"].apply(lambda x: eval(x)[1] if isinstance(x, str) else x[1])
    return df


def plot_format_mode_percentage(df: pd.DataFrame, save_path: str | None = None, max_filesize_kb: int | None = None):
    if max_filesize_kb:
        df = df[df["filesize_kb"] <= max_filesize_kb]

    df["format_mode"] = df["format"].astype(str) + " / " + df["mode"].astype(str)
    counts = df["format_mode"].value_counts()
    percentages = (counts / len(df) * 100).round(1)

    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(percentages.index, percentages.values, color=sns.color_palette("husl", len(percentages)))
    ax.set_xlabel("Percentage (%)")
    ax.set_title("Distribution of Format + Mode")
    ax.bar_label(bars, fmt="%.1f%%")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()
    return percentages


def plot_filesize_distribution(
    df: pd.DataFrame,
    save_path: str | None = None,
    min_filesize_kb: int | None = None,
    max_filesize_kb: int | None = None,
):
    data = df["filesize_kb"]

    if min_filesize_kb:
        data = data[min_filesize_kb <= data]
    if max_filesize_kb:
        data = data[data <= max_filesize_kb]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].hist(data, bins=50, edgecolor="black", alpha=0.7)
    axes[0].set_xlabel("Filesize (KB)")
    axes[0].set_ylabel("Count")
    axes[0].set_title("Filesize Distribution (Histogram)")
    axes[0].axvline(data.mean(), color="red", linestyle="--", label=f"Mean: {data.mean():.1f} KB")
    axes[0].legend()

    axes[1].boxplot(data, vert=True)
    axes[1].set_ylabel("Filesize (KB)")
    axes[1].set_title("Filesize Distribution (Boxplot)")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_bpp_distribution(
    df: pd.DataFrame, save_path: str | None = None, bpp_from: int | None = None, bpp_to: int | None = None
):
    data = df["bpp"]

    if bpp_to:
        data = data[data <= bpp_to]
    if bpp_from:
        data = data[bpp_from <= data]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].hist(data, bins=50, edgecolor="black", alpha=0.7, color="green")
    axes[0].set_xlabel("Bits Per Pixel")
    axes[0].set_ylabel("Count")
    axes[0].set_title("BPP Distribution (Histogram)")
    axes[0].axvline(data.mean(), color="red", linestyle="--", label=f"Mean: {data.mean():.2f}")
    axes[0].legend()

    axes[1].boxplot(data, vert=True)
    axes[1].set_ylabel("Bits Per Pixel")
    axes[1].set_title("BPP Distribution (Boxplot)")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_format_distribution(df: pd.DataFrame, save_path: str | None = None):
    counts = df["format"].value_counts()

    fig, ax = plt.subplots(figsize=(8, 8))
    colors = sns.color_palette("Set2", len(counts))
    wedges, texts, autotexts = ax.pie(counts, labels=counts.index, autopct="%1.1f%%", colors=colors, startangle=90)
    ax.set_title("Format Distribution")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()
    return counts


def plot_mode_distribution(df: pd.DataFrame, save_path: str | None = None):
    counts = df["mode"].value_counts()

    fig, ax = plt.subplots(figsize=(8, 8))
    colors = sns.color_palette("Set3", len(counts))
    wedges, texts, autotexts = ax.pie(counts, labels=counts.index, autopct="%1.1f%%", colors=colors, startangle=90)
    ax.set_title("Mode Distribution")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()
    return counts


def plot_filesize_by_format(df: pd.DataFrame, save_path: str | None = None):
    fig, ax = plt.subplots(figsize=(12, 6))
    df.boxplot(column="filesize_kb", by="format", ax=ax)
    ax.set_xlabel("Format")
    ax.set_ylabel("Filesize (KB)")
    ax.set_title("Filesize Distribution by Format")
    plt.suptitle("")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_bpp_by_format(df: pd.DataFrame, save_path: str | None = None):
    fig, ax = plt.subplots(figsize=(12, 6))
    df.boxplot(column="bpp", by="format", ax=ax)
    ax.set_xlabel("Format")
    ax.set_ylabel("Bits Per Pixel")
    ax.set_title("BPP Distribution by Format")
    plt.suptitle("")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_filesize_vs_bpp(df: pd.DataFrame, save_path: str | None = None):
    fig, ax = plt.subplots(figsize=(10, 8))
    scatter = ax.scatter(df["bpp"], df["filesize_kb"], alpha=0.5, c=df["pixels"], cmap="viridis", s=20)
    ax.set_xlabel("Bits Per Pixel")
    ax.set_ylabel("Filesize (KB)")
    ax.set_title("Filesize vs BPP (color = total pixels)")
    plt.colorbar(scatter, label="Pixels")

    corr = df["bpp"].corr(df["filesize_kb"])
    ax.text(
        0.05, 0.95, f"Pearson correlation: {corr:.3f}", transform=ax.transAxes, fontsize=10, verticalalignment="top"
    )

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_processing_time_distribution(df: pd.DataFrame, save_path: str | None = None):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].hist(df["processing_time"], bins=50, edgecolor="black", alpha=0.7, color="orange")
    axes[0].set_xlabel("Processing Time (seconds)")
    axes[0].set_ylabel("Count")
    axes[0].set_title("Processing Time Distribution")
    axes[0].axvline(
        df["processing_time"].mean(), color="red", linestyle="--", label=f"Mean: {df['processing_time'].mean():.3f}s"
    )
    axes[0].legend()

    axes[1].scatter(df["filesize_kb"], df["processing_time"], alpha=0.5)
    axes[1].set_xlabel("Filesize (KB)")
    axes[1].set_ylabel("Processing Time (seconds)")
    axes[1].set_title("Processing Time vs Filesize")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_animated_vs_static(df: pd.DataFrame, save_path: str | None = None):
    df["animated"] = df["is_animated"].apply(lambda x: "Animated" if x and x != "False" else "Static")
    counts = df["animated"].value_counts()

    fig, ax = plt.subplots(figsize=(6, 6))
    colors = ["#66b3ff", "#ff9999"]
    wedges, texts, autotexts = ax.pie(counts, labels=counts.index, autopct="%1.1f%%", colors=colors, startangle=90)
    ax.set_title("Animated vs Static Images")

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()
    return counts


def plot_image_dimensions(df: pd.DataFrame, save_path: str | None = None):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].hist(df["width"], bins=50, edgecolor="black", alpha=0.7, color="purple")
    axes[0].set_xlabel("Width (pixels)")
    axes[0].set_ylabel("Count")
    axes[0].set_title("Width Distribution")

    axes[1].hist(df["height"], bins=50, edgecolor="black", alpha=0.7, color="teal")
    axes[1].set_xlabel("Height (pixels)")
    axes[1].set_ylabel("Count")
    axes[1].set_title("Height Distribution")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def plot_pixels_distribution(df: pd.DataFrame, save_path: str | None = None):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(df["pixels"], bins=50, edgecolor="black", alpha=0.7, color="coral")
    ax.set_xlabel("Total Pixels (width × height)")
    ax.set_ylabel("Count")
    ax.set_title("Total Pixels Distribution")
    ax.ticklabel_format(style="scientific", axis="x", scilimits=(0, 0))

    if save_path:
        plt.savefig(save_path, bbox_inches="tight")
    plt.show()


def generate_summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    summary = pd.DataFrame(
        {
            "Metric": [
                "Total Images",
                "Mean Filesize (KB)",
                "Median Filesize (KB)",
                "Mean BPP",
                "Median BPP",
                "Mean Processing Time (s)",
                "Mean Width",
                "Mean Height",
                "Mean Pixels",
            ],
            "Value": [
                len(df),
                df["filesize_kb"].mean(),
                df["filesize_kb"].median(),
                df["bpp"].mean(),
                df["bpp"].median(),
                df["processing_time"].mean(),
                df["width"].mean(),
                df["height"].mean(),
                df["pixels"].mean(),
            ],
        }
    )
    return summary


def run_all_analysis(csv_path: str, output_dir: str = "analysis_results", max_filesize_kb: int = 10000):
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    df = load_data(csv_path)

    print("=== Generating Analysis ===\n")

    print("1. Format + Mode Distribution")
    plot_format_mode_percentage(
        df, save_path=str(output_path / "format_mode_percentage.png"), max_filesize_kb=max_filesize_kb
    )

    print("2. Filesize Distribution")
    plot_filesize_distribution(
        df, save_path=str(output_path / "filesize_distribution.png"), max_filesize_kb=max_filesize_kb
    )

    print("3. BPP Distribution")
    plot_bpp_distribution(df, save_path=str(output_path / "bpp_distribution.png"))

    print("4. Format Distribution")
    plot_format_distribution(df, save_path=str(output_path / "format_distribution.png"))

    print("5. Mode Distribution")
    plot_mode_distribution(df, save_path=str(output_path / "mode_distribution.png"))

    print("6. Filesize by Format")
    plot_filesize_by_format(df, save_path=str(output_path / "filesize_by_format.png"))

    print("7. BPP by Format")
    plot_bpp_by_format(df, save_path=str(output_path / "bpp_by_format.png"))

    print("8. Filesize vs BPP")
    plot_filesize_vs_bpp(df, save_path=str(output_path / "filesize_vs_bpp.png"))

    print("9. Processing Time Distribution")
    plot_processing_time_distribution(df, save_path=str(output_path / "processing_time.png"))

    print("10. Animated vs Static")
    plot_animated_vs_static(df, save_path=str(output_path / "animated_vs_static.png"))

    print("11. Image Dimensions")
    plot_image_dimensions(df, save_path=str(output_path / "dimensions.png"))

    print("12. Total Pixels Distribution")
    plot_pixels_distribution(df, save_path=str(output_path / "pixels_distribution.png"))

    print("\n=== Summary Statistics ===")
    print(generate_summary_stats(df).to_string(index=False))

    print(f"\nAll plots saved to: {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python image_analysis.py <path_to_csv>")
        sys.exit(1)
    run_all_analysis(sys.argv[1])
